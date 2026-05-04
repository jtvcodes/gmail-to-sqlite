import concurrent.futures
import base64
import logging
import os
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError, Error as GoogleApiError
from peewee import IntegrityError

from . import db, message
from .constants import (
    GMAIL_API_VERSION,
    MAX_RESULTS_PER_PAGE,
    MAX_RETRY_ATTEMPTS,
    RETRY_DELAY_SECONDS,
    PROGRESS_LOG_INTERVAL,
    COLLECTION_LOG_INTERVAL,
)


class SyncError(Exception):
    """Custom exception for synchronization errors."""

    pass


# Thread-local storage for Gmail API service instances
_thread_local = threading.local()


def _get_thread_service(credentials: Any) -> Any:
    """
    Gets or creates a Gmail API service for the current thread.

    Args:
        credentials: The credentials object for API authentication.

    Returns:
        The Gmail API service object for this thread.
    """
    if not hasattr(_thread_local, "service"):
        _thread_local.service = _create_service(credentials)
    return _thread_local.service


def _save_attachments_to_disk(service: Any, msg: Any, data_dir: str) -> None:
    """Download real attachments to data/attachments/<message_id>/ while tokens are fresh.

    Skips attachments that are already cached, have no filename, or have no
    attachment_id (inline data is already stored in the DB).
    """
    attachments = getattr(msg, "attachments", [])
    if not attachments:
        return

    for att in attachments:
        # Skip MIME container parts and attachments without a usable filename/id
        if not att.filename or not att.attachment_id:
            continue
        if att.mime_type.startswith("multipart/"):
            continue

        cache_dir = os.path.join(data_dir, "attachments", msg.id)
        cache_path = os.path.join(cache_dir, att.filename)

        if os.path.isfile(cache_path):
            continue  # already cached

        try:
            result = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg.id, id=att.attachment_id)
                .execute()
            )
            data = base64.urlsafe_b64decode(result.get("data", ""))
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(data)
            logging.info(f"Cached attachment {att.filename} for message {msg.id}")
        except Exception as e:
            logging.warning(f"Could not download attachment {att.filename} for message {msg.id}: {e}")


def _fetch_message(
    service: Any,
    message_id: str,
    labels: Dict[str, str],
    check_interrupt: Optional[Callable[[], bool]] = None,
) -> message.Message:
    """
    Fetches a single message from Gmail API with retry logic and robust error handling.

    Args:
        service: The Gmail API service object.
        message_id: The ID of the message to fetch.
        labels: Dictionary mapping label IDs to label names.
        check_interrupt: Optional callback that returns True if process should be interrupted.

    Returns:
        Message: The parsed message object.

    Raises:
        InterruptedError: If the process was interrupted.
        SyncError: If the message cannot be fetched after all retries.
    """
    for attempt in range(MAX_RETRY_ATTEMPTS):
        if check_interrupt and check_interrupt():
            raise InterruptedError("Process was interrupted")

        try:
            raw_msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="raw")
                .execute()
            )

            def _apply_envelope(m: message.Message, envelope: dict) -> None:
                """Stamp Gmail envelope fields onto a Message object."""
                from datetime import datetime as _dt
                m.id = envelope.get("id", message_id)
                m.thread_id = envelope.get("threadId", "")
                m.size = envelope.get("sizeEstimate", m.size or 0)
                label_ids = envelope.get("labelIds", [])
                m.labels = [labels[lid] for lid in label_ids if lid in labels]
                m.is_read = "UNREAD" not in label_ids
                m.is_outgoing = "SENT" in label_ids
                if "internalDate" in envelope:
                    m.timestamp = _dt.fromtimestamp(int(envelope["internalDate"]) / 1000)

            if "raw" not in raw_msg:
                logging.warning(
                    f"Message {message_id} response missing 'raw' field; storing raw=None"
                )
                msg = message.Message()
                _apply_envelope(msg, raw_msg)
                msg.raw = None
                return msg

            try:
                decoded_str = base64.urlsafe_b64decode(raw_msg["raw"]).decode("utf-8")
            except Exception as decode_err:
                logging.error(
                    f"Failed to decode base64url payload for message {message_id}: {decode_err}"
                )
                msg = message.Message()
                _apply_envelope(msg, raw_msg)
                msg.raw = None
                return msg

            msg = message.Message.from_raw_source(decoded_str, labels)
            # RFC 2822 body doesn't contain Gmail envelope fields — pull from API response.
            _apply_envelope(msg, raw_msg)
            return msg

        except HttpError as e:
            if e.resp.status >= 500 and attempt < MAX_RETRY_ATTEMPTS - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed for message {message_id} "
                    f"due to server error {e.resp.status}. Retrying in {RETRY_DELAY_SECONDS}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = (
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts "
                    f"due to HttpError {e.resp.status}: {str(e)}"
                )
                logging.error(error_msg)
                raise SyncError(error_msg)

        except (TimeoutError, socket.timeout) as e:
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed for message {message_id} "
                    f"due to timeout. Retrying in {RETRY_DELAY_SECONDS}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = (
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts "
                    f"due to timeout: {str(e)}"
                )
                logging.error(error_msg)
                raise SyncError(error_msg)

        except Exception as e:
            logging.error(
                f"Unexpected error processing message {message_id} on attempt {attempt + 1}: {str(e)}"
            )
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = f"Failed to fetch message {message_id} after {MAX_RETRY_ATTEMPTS} attempts"
                logging.error(error_msg)
                raise SyncError(error_msg)

    # This should never be reached due to the exception handling above
    raise SyncError(f"Unexpected error: failed to fetch message {message_id}")


def get_labels(service: Any) -> Dict[str, str]:
    """
    Retrieves all labels from the Gmail API.

    Args:
        service: The Gmail API service object.

    Returns:
        Dict[str, str]: Mapping of label IDs to label names.

    Raises:
        SyncError: If labels cannot be retrieved.
    """
    try:
        labels = {}
        response = service.users().labels().list(userId="me").execute()
        for label in response.get("labels", []):
            labels[label["id"]] = label["name"]
        return labels
    except (HttpError, GoogleApiError) as e:
        raise SyncError(f"Failed to retrieve labels: {e}")


def _create_service(credentials: Any) -> Any:
    """
    Creates a new Gmail API service object.

    Args:
        credentials: The credentials object for API authentication.

    Returns:
        The Gmail API service object.

    Raises:
        SyncError: If service creation fails.
    """
    try:
        return build(
            "gmail", GMAIL_API_VERSION, credentials=credentials, cache_discovery=False
        )
    except Exception as e:
        raise SyncError(f"Failed to create Gmail service: {e}")


def get_message_ids_from_gmail(
    service: Any,
    query: Optional[List[str]] = None,
    limit: Optional[int] = None,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """
    Fetches message IDs from Gmail matching the query.

    Args:
        service: The Gmail API service object.
        query: Optional list of query strings to filter messages.
        limit: If set, stop collecting after this many IDs (skips pagination).
        check_shutdown: Callback that returns True if shutdown is requested.

    Returns:
        List[str]: List of message IDs from Gmail.

    Raises:
        SyncError: If message ID collection fails.
    """
    all_message_ids = []
    page_token = None
    collected_count = 0

    if limit is not None:
        logging.info(f"Collecting up to {limit} message ID(s) from Gmail...")
    else:
        logging.info("Collecting all message IDs from Gmail...")

    try:
        while not (check_shutdown and check_shutdown()):
            # When a limit is set, ask Gmail for exactly that many in one call
            page_size = min(limit, MAX_RESULTS_PER_PAGE) if limit is not None else MAX_RESULTS_PER_PAGE
            list_params = {
                "userId": "me",
                "maxResults": page_size,
            }

            if page_token:
                list_params["pageToken"] = page_token

            if query:
                list_params["q"] = " | ".join(query)

            results = service.users().messages().list(**list_params).execute()
            messages_page = results.get("messages", [])

            for m_info in messages_page:
                all_message_ids.append(m_info["id"])
                collected_count += 1

                if limit is not None and collected_count >= limit:
                    logging.info(f"Reached limit of {limit} message ID(s).")
                    return all_message_ids

                if collected_count % COLLECTION_LOG_INTERVAL == 0:
                    logging.info(
                        f"Collected {collected_count} message IDs from Gmail..."
                    )

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except KeyboardInterrupt:
        logging.info("Message ID collection interrupted by user")
    except Exception as e:
        raise SyncError(f"Failed to collect message IDs: {e}")

    if check_shutdown and check_shutdown():
        logging.info(
            "Shutdown requested during message ID collection. Exiting gracefully."
        )
        return []

    logging.info(f"Collected {len(all_message_ids)} message IDs from Gmail")
    return all_message_ids


def _detect_and_mark_deleted_messages(
    gmail_message_ids: List[str], check_shutdown: Optional[Callable[[], bool]] = None
) -> Optional[int]:
    """
    Helper function to detect and mark deleted messages based on comparison
    between Gmail message IDs and database message IDs.

    Args:
        gmail_message_ids (list): List of message IDs from Gmail.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: Number of messages newly marked as deleted, or None if no action taken.
    """
    try:
        db_message_ids = set(db.get_all_message_ids())
        logging.info(
            f"Retrieved {len(db_message_ids)} message IDs from database for deletion detection"
        )

        if not db_message_ids:
            logging.info("No messages in database to check for deletion")
            return None

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during deletion detection. Exiting gracefully."
            )
            return None

        already_deleted_ids = set(db.get_deleted_message_ids())
        if already_deleted_ids:
            logging.info(
                f"Found {len(already_deleted_ids)} already deleted messages to skip"
            )

        gmail_ids_set = set(gmail_message_ids)
        potential_deleted_ids = db_message_ids - gmail_ids_set
        new_deleted_ids = (
            list(potential_deleted_ids - already_deleted_ids)
            if already_deleted_ids
            else list(potential_deleted_ids)
        )

        if new_deleted_ids:
            logging.info(f"Found {len(new_deleted_ids)} new deleted messages to mark")
            db.mark_messages_as_deleted(new_deleted_ids)
            logging.info(
                f"Deletion sync complete. {len(new_deleted_ids)} messages newly marked as deleted."
            )
            return len(new_deleted_ids)
        else:
            logging.info("No new deleted messages found")
            return None
    except Exception as e:
        logging.error(f"Error during deletion detection: {str(e)}")
        return None


def all_messages(
    credentials: Any,
    data_dir: str,
    full_sync: bool = True,
    force: bool = False,
    num_workers: int = 4,
    limit: Optional[int] = None,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials, in parallel.
    Also detects and marks deleted messages.

    Args:
        credentials (object): The credentials object used to authenticate the API request.
        data_dir (str): Directory where attachments are cached.
        full_sync (bool): Whether to do a full sync or not.
        force (bool): Re-fetch all messages even if already in the DB.
        num_workers (int): Number of worker threads for parallel fetching.
        limit (int, optional): Stop after fetching this many messages (for testing).
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: The number of messages successfully synced.
    """
    executor = None
    future_to_id = {}

    try:
        from datetime import timezone, datetime as _datetime
        _EPOCH = _datetime(1970, 1, 1, tzinfo=timezone.utc)

        def _safe_timestamp(dt):
            """Return Unix timestamp, clamping pre-epoch dates to 0 (Windows fix)."""
            try:
                return int(dt.timestamp())
            except (OSError, OverflowError, ValueError):
                return 0

        query = []
        if not full_sync:
            last = db.last_indexed()
            if last:
                # Only fetch messages newer than the most recently indexed one
                query.append(f"after:{_safe_timestamp(last)}")
        service = _create_service(credentials)
        labels = get_labels(service)

        all_message_ids = get_message_ids_from_gmail(service, query, limit=limit, check_shutdown=check_shutdown)
        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during message ID collection. Exiting gracefully."
            )
            return 0

        if full_sync:
            _detect_and_mark_deleted_messages(all_message_ids, check_shutdown)

        # For full sync, skip IDs already in the DB to avoid re-fetching,
        # EXCEPT for messages where raw is NULL (need to fetch raw source).
        # --force skips all filtering and re-fetches everything.
        if full_sync and all_message_ids and not force:
            known_ids = set(db.get_all_message_ids())
            needs_raw_fix = set(db.get_message_ids_missing_raw())
            missing_ids = [mid for mid in all_message_ids if mid not in known_ids or mid in needs_raw_fix]
            logging.info(
                f"Full sync: {len(all_message_ids)} total in Gmail, "
                f"{len(known_ids)} already in DB, "
                f"{len(needs_raw_fix)} missing raw, "
                f"{len(missing_ids)} to fetch."
            )
            all_message_ids = missing_ids
        elif force:
            logging.info(f"Force sync: re-fetching all {len(all_message_ids)} messages.")

        # Apply test limit as a safety net (collection should already be limited)
        if limit is not None and len(all_message_ids) > limit:
            all_message_ids = all_message_ids[:limit]

        logging.info(f"Found {len(all_message_ids)} messages to sync.")

        total_synced_count = 0
        processed_count = 0

        def thread_worker(message_id: str) -> bool:
            if check_shutdown and check_shutdown():
                return False

            service = _get_thread_service(credentials)

            try:
                msg = _fetch_message(
                    service,
                    message_id,
                    labels,
                    check_interrupt=check_shutdown,
                )
                try:
                    db.create_message(msg)
                    logging.info(
                        f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
                    )
                    # Download attachments to disk while tokens are still fresh
                    _save_attachments_to_disk(service, msg, data_dir)
                    return True
                except IntegrityError as e:
                    logging.error(
                        f"Could not process message {message_id} due to integrity error: {str(e)}"
                    )
                    return False
            except InterruptedError:
                logging.info(f"Message fetch for {message_id} was interrupted")
                return False
            except Exception as e:
                logging.error(f"Failed to fetch message {message_id}: {str(e)}")
                return False

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_workers
        ) as executor_instance:
            executor = executor_instance
            future_to_id = {
                executor.submit(thread_worker, msg_id): msg_id
                for msg_id in all_message_ids
            }

            for future in concurrent.futures.as_completed(future_to_id):
                if check_shutdown and check_shutdown():
                    continue

                message_id = future_to_id[future]
                processed_count += 1
                try:
                    if not future.cancelled():
                        if future.result():
                            total_synced_count += 1
                    if (
                        processed_count % PROGRESS_LOG_INTERVAL == 0
                        or processed_count == len(all_message_ids)
                    ):
                        logging.info(
                            f"Processed {processed_count}/{len(all_message_ids)} messages..."
                        )
                except concurrent.futures.CancelledError:
                    logging.info(
                        f"Task for message {message_id} was cancelled due to shutdown"
                    )
                except Exception as exc:
                    logging.error(
                        f"Message ID {message_id} generated an exception during future processing: {exc}"
                    )

        if check_shutdown and check_shutdown():
            logging.info("Sync process was interrupted. Partial results saved.")
        else:
            logging.info(
                f"Total messages successfully synced: {total_synced_count} out of {len(all_message_ids)}"
            )
        return total_synced_count
    except Exception as e:
        logging.error(f"Unexpected error during sync: {e}")
        raise SyncError(f"Sync failed: {e}") from e


def sync_deleted_messages(
    credentials: Any, check_shutdown: Optional[Callable[[], bool]] = None
) -> Optional[int]:
    """
    Compares message IDs in Gmail with those in the database and marks missing messages as deleted.
    This function only updates the is_deleted flag and doesn't download full message content.
    It skips messages that are already marked as deleted for efficiency.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: Number of messages marked as deleted.
    """
    try:
        service = _create_service(credentials)
        gmail_message_ids = get_message_ids_from_gmail(
            service, check_shutdown=check_shutdown
        )

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during message ID collection. Exiting gracefully."
            )
            return None

        return _detect_and_mark_deleted_messages(gmail_message_ids, check_shutdown)
    except Exception as e:
        logging.error(f"Error during deletion sync: {str(e)}")
        return None


def single_message(
    credentials: Any,
    message_id: str,
    data_dir: str = "",
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Syncs a single message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        None
    """
    try:
        service = _create_service(credentials)
        labels = get_labels(service)

        if check_shutdown and check_shutdown():
            logging.info("Shutdown requested. Exiting gracefully.")
            return None

        msg = _fetch_message(
            service,
            message_id,
            labels,
            check_interrupt=check_shutdown,
        )
        if check_shutdown and check_shutdown():
            logging.info("Shutdown requested after message fetch. Exiting gracefully.")
            return None

        try:
            db.create_message(msg)
            logging.info(
                f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
            )
            if data_dir:
                _save_attachments_to_disk(service, msg, data_dir)
        except IntegrityError as e:
            logging.error(
                f"Could not process message {message_id} due to integrity error: {str(e)}"
            )
    except InterruptedError:
        logging.info(f"Message fetch for {message_id} was interrupted")
    except Exception as e:
        logging.error(f"Failed to fetch message {message_id}: {str(e)}")
