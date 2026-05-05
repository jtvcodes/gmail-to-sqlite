import concurrent.futures
import base64
import logging
import socket
import threading
import time
from datetime import datetime
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
    DB_WRITE_BATCH_SIZE,
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
                raw_bytes = base64.urlsafe_b64decode(raw_msg["raw"])
                try:
                    decoded_str = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    logging.warning(
                        f"UTF-8 decode failed for message {message_id}, falling back to latin-1"
                    )
                    decoded_str = raw_bytes.decode("latin-1")
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
) -> tuple:
    """
    Fetches message IDs from Gmail matching the query.

    Args:
        service: The Gmail API service object.
        query: Optional list of query strings to filter messages.
        limit: If set, stop collecting after this many IDs (skips pagination).
        check_shutdown: Callback that returns True if shutdown is requested.

    Returns:
        Tuple[List[str], Optional[str]]: (message_ids, history_id) where history_id
        is the historyId from the first page response (or from getProfile if absent),
        or None if unavailable.

    Raises:
        SyncError: If message ID collection fails.
    """
    all_message_ids = []
    page_token = None
    collected_count = 0
    captured_history_id: Optional[str] = None
    first_page = True

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

            # Capture historyId from the first page response
            if first_page:
                first_page = False
                captured_history_id = results.get("historyId") or None
                if captured_history_id is None:
                    # Fall back to getProfile for the current historyId
                    try:
                        profile = service.users().getProfile(userId="me").execute()
                        captured_history_id = profile.get("historyId") or None
                    except Exception as profile_err:
                        logging.warning(f"Could not fetch historyId from getProfile: {profile_err}")

            messages_page = results.get("messages", [])
            page_ids = []

            for m_info in messages_page:
                mid = m_info["id"]
                all_message_ids.append(mid)
                page_ids.append(mid)
                collected_count += 1

                if limit is not None and collected_count >= limit:
                    logging.info(f"Reached limit of {limit} message ID(s).")
                    # Persist this partial page before returning
                    if page_ids:
                        try:
                            db.upsert_gmail_index(page_ids)
                        except Exception as idx_err:
                            logging.warning(f"Could not update gmail_index: {idx_err}")
                    return all_message_ids, captured_history_id

                if collected_count % COLLECTION_LOG_INTERVAL == 0:
                    logging.info(
                        f"Collected {collected_count} message IDs from Gmail..."
                    )

            # Persist each page to gmail_index as it arrives
            if page_ids:
                try:
                    db.upsert_gmail_index(page_ids)
                except Exception as idx_err:
                    logging.warning(f"Could not update gmail_index: {idx_err}")

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
        return [], None

    logging.info(f"Collected {len(all_message_ids)} message IDs from Gmail")
    return all_message_ids, captured_history_id


def get_changed_message_ids_from_history(
    service: Any,
    start_history_id: str,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> tuple:
    """
    Use the Gmail History API to get changes since start_history_id.

    Returns:
        Tuple[List[str], List[str], List[tuple], Optional[str]]:
            (added_ids, deleted_ids, label_changes, latest_history_id)
            - added_ids: message IDs that were added/received
            - deleted_ids: message IDs that were permanently deleted
            - label_changes: list of (message_id, label_ids_added, label_ids_removed)
            - latest_history_id: the most recent historyId seen, or None

    Raises:
        SyncError: With history_expired=True when Gmail returns 404 (history too old).
        SyncError: For other API errors.
    """
    added_ids: List[str] = []
    deleted_ids: List[str] = []
    label_changes: List[tuple] = []
    latest_history_id: Optional[str] = None
    page_token = None

    logging.info(f"Fetching history since historyId={start_history_id}...")

    try:
        while not (check_shutdown and check_shutdown()):
            list_params: dict = {
                "userId": "me",
                "startHistoryId": start_history_id,
                "historyTypes": ["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"],
            }
            if page_token:
                list_params["pageToken"] = page_token

            results = service.users().history().list(**list_params).execute()

            page_history_id = results.get("historyId")
            if page_history_id:
                latest_history_id = page_history_id

            for record in results.get("history", []):
                for added in record.get("messagesAdded", []):
                    msg_id = added.get("message", {}).get("id")
                    if msg_id:
                        added_ids.append(msg_id)
                for deleted in record.get("messagesDeleted", []):
                    msg_id = deleted.get("message", {}).get("id")
                    if msg_id:
                        deleted_ids.append(msg_id)
                for lbl_added in record.get("labelsAdded", []):
                    msg_id = lbl_added.get("message", {}).get("id")
                    added_labels = lbl_added.get("labelIds", [])
                    if msg_id and added_labels:
                        label_changes.append((msg_id, added_labels, []))
                for lbl_removed in record.get("labelsRemoved", []):
                    msg_id = lbl_removed.get("message", {}).get("id")
                    removed_labels = lbl_removed.get("labelIds", [])
                    if msg_id and removed_labels:
                        label_changes.append((msg_id, [], removed_labels))

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except HttpError as e:
        if e.resp.status == 404:
            err = SyncError(f"Gmail history expired (404): {e}")
            err.history_expired = True  # type: ignore[attr-defined]
            raise err
        raise SyncError(f"History API error {e.resp.status}: {e}")
    except SyncError:
        raise
    except Exception as e:
        raise SyncError(f"Failed to fetch history: {e}")

    logging.info(
        f"History sync: {len(added_ids)} added, {len(deleted_ids)} deleted, "
        f"{len(label_changes)} label changes, latest historyId={latest_history_id}"
    )
    return added_ids, deleted_ids, label_changes, latest_history_id


def _apply_history_label_changes(
    label_changes: List[tuple],
    labels: Dict[str, str],
) -> None:
    """Apply label/read/delete changes from history to already-synced messages.

    Args:
        label_changes: List of (message_id, added_label_ids, removed_label_ids).
        labels: Mapping of label ID → label name.
    """
    if not label_changes:
        return

    # Consolidate changes per message_id
    changes_by_id: Dict[str, Dict] = {}
    for msg_id, added, removed in label_changes:
        if msg_id not in changes_by_id:
            changes_by_id[msg_id] = {"added": set(), "removed": set()}
        changes_by_id[msg_id]["added"].update(added)
        changes_by_id[msg_id]["removed"].update(removed)

    updated = 0
    for msg_id, change in changes_by_id.items():
        try:
            row = db.Message.get_or_none(db.Message.message_id == msg_id)
            if row is None:
                continue  # not yet downloaded — will be handled when synced

            added_ids = change["added"]
            removed_ids = change["removed"]

            # Determine new is_read state
            is_read = row.is_read
            if "UNREAD" in added_ids:
                is_read = False
            if "UNREAD" in removed_ids:
                is_read = True

            # Determine is_deleted state
            is_deleted = row.is_deleted
            if "TRASH" in added_ids or "SPAM" in added_ids:
                is_deleted = True
            if "TRASH" in removed_ids or "SPAM" in removed_ids:
                is_deleted = False

            # Rebuild labels list
            current_label_ids = set()
            # Map current label names back to IDs for manipulation
            name_to_id = {v: k for k, v in labels.items()}
            for lbl_name in (row.labels or []):
                lid = name_to_id.get(lbl_name)
                if lid:
                    current_label_ids.add(lid)
            current_label_ids.update(added_ids)
            current_label_ids -= removed_ids
            new_labels = [labels[lid] for lid in current_label_ids if lid in labels]

            db.Message.update(
                is_read=is_read,
                is_deleted=is_deleted,
                labels=new_labels,
                last_indexed=datetime.now(),
            ).where(db.Message.message_id == msg_id).execute()
            updated += 1
        except Exception as e:
            logging.warning(f"Could not apply label change for {msg_id}: {e}")

    if updated:
        logging.info(f"Applied label/read/delete changes to {updated} messages.")


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
    verbose: bool = False,
) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials, in parallel.
    Also detects and marks deleted messages.

    On subsequent runs (full_sync=True, force=False), uses the Gmail History API
    to perform an incremental sync instead of re-paginating all message IDs.

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
                query.append(f"after:{_safe_timestamp(last)}")

        logging.info("STATUS: Connecting…")
        service = _create_service(credentials)
        labels = get_labels(service)

        # ── Step 1: Apply history changes (read/delete/label updates) ──────────
        stored_history_id = db.get_sync_state("history_id")
        if stored_history_id is not None and not force:
            logging.info("STATUS: Checking for changes…")
            try:
                added_ids, deleted_ids, label_changes, new_history_id = \
                    get_changed_message_ids_from_history(
                        service, stored_history_id, check_shutdown=check_shutdown
                    )
                # Apply label/read/delete changes to already-synced messages
                _apply_history_label_changes(label_changes, labels)
                # Mark deleted in both tables
                if deleted_ids:
                    db.mark_messages_as_deleted(deleted_ids)
                    db.mark_gmail_index_deleted(deleted_ids)
                # Register newly added IDs in the index (synced=False)
                if added_ids:
                    db.upsert_gmail_index(added_ids)
                if new_history_id:
                    db.set_sync_state("history_id", new_history_id)
                logging.info(
                    f"History applied: {len(added_ids)} new, {len(deleted_ids)} deleted, "
                    f"{len(label_changes)} label changes."
                )
            except SyncError as e:
                if getattr(e, "history_expired", False):
                    logging.warning("History expired — will refresh full ID list.")
                    stored_history_id = None
                else:
                    raise

        # ── Step 2: Collect all Gmail IDs if needed ───────────────────────────
        # Needed when: first run, history expired, --force, or --delta
        index_count = db.get_gmail_index_count()
        needs_full_list = (
            force
            or not full_sync
            or stored_history_id is None
            or index_count["total"] == 0
        )

        if needs_full_list:
            logging.info("STATUS: Collecting message IDs…")
            logging.info("Collecting full Gmail ID list...")
            all_gmail_ids, new_history_id = get_message_ids_from_gmail(
                service, query, limit=limit, check_shutdown=check_shutdown
            )
            if check_shutdown and check_shutdown():
                logging.info("Shutdown requested during ID collection. Exiting.")
                return 0
            if new_history_id:
                db.set_sync_state("history_id", new_history_id)
            # IDs already upserted per-page inside get_message_ids_from_gmail.
            # Detect deletions for full syncs (not limited test runs).
            if full_sync and not limit:
                _detect_and_mark_deleted_messages(all_gmail_ids, check_shutdown)
            if force:
                logging.info(f"Force sync: re-downloading all {len(all_gmail_ids)} messages.")
                all_message_ids = all_gmail_ids
            else:
                all_message_ids = all_gmail_ids  # will be filtered below
        else:
            all_message_ids = []

        # ── Step 3: Determine what to actually download ───────────────────────
        if force:
            # Re-download everything
            pass  # all_message_ids already set above
        else:
            # Download: unsynced from index + messages missing raw
            unsynced = set(db.get_unsynced_gmail_ids())
            needs_raw = set(db.get_message_ids_missing_raw())
            if needs_full_list:
                gmail_set = set(all_message_ids)
                # IDs Gmail returned that aren't in the messages table yet
                # (covers new messages whose gmail_index row was already synced=True
                # from a previous run, which would be missed by the unsynced set)
                existing = set(db.get_all_message_ids())
                not_in_db = gmail_set - existing
                # Also pick up anything the index knows is unsynced within this batch
                also_unsynced = unsynced & gmail_set
                all_message_ids = list(not_in_db | also_unsynced | (needs_raw & gmail_set))
            else:
                # History path already updated the index — just fetch unsynced
                all_message_ids = list(unsynced | needs_raw)

            logging.info(
                f"To fetch: {len(all_message_ids)} "
                f"({len(unsynced)} unsynced in index, {len(needs_raw)} missing raw)."
            )

        # Apply test limit as a safety net (collection should already be limited)
        if limit is not None and len(all_message_ids) > limit:
            all_message_ids = all_message_ids[:limit]

        logging.info(f"Found {len(all_message_ids)} messages to sync.")
        if len(all_message_ids) > 0:
            logging.info(f"STATUS: Downloading {len(all_message_ids)} messages…")
        else:
            logging.info("STATUS: Done — 0 messages to download")

        total_synced_count = 0
        processed_count = 0

        # Each worker fetches a message and returns the parsed Message object
        # (or None on failure).  DB writes are batched on the main thread to
        # avoid per-message SQLite lock contention.
        def thread_worker(message_id: str):
            """Fetch one message and return (message_id, msg) or (message_id, None)."""
            if check_shutdown and check_shutdown():
                return message_id, None

            svc = _get_thread_service(credentials)
            try:
                msg = _fetch_message(svc, message_id, labels, check_interrupt=check_shutdown)
                return message_id, msg
            except InterruptedError:
                return message_id, None
            except SyncError:
                raise
            except Exception as e:
                logging.error(f"Failed to fetch message {message_id}: {e}")
                return message_id, None

        def flush_batch(batch):
            """Write a batch of (message_id, msg) pairs atomically.

            All message writes happen inside a single SQLite transaction.
            mark_gmail_index_synced is only called after every write in the
            batch has committed successfully — never on a partial batch.
            """
            if not batch:
                return 0

            from playhouse.sqlite_ext import SqliteDatabase as _SqliteDb
            conn = db.database_proxy.obj  # the underlying SqliteDatabase

            successfully_saved = []
            with conn.atomic():
                for mid, msg in batch:
                    try:
                        db.create_message(msg)
                        successfully_saved.append(mid)
                        if verbose:
                            logging.info(
                                f"Successfully synced message {msg.id} from {msg.timestamp}"
                            )
                        else:
                            logging.info(f"Successfully synced message {mid}")
                    except (db.DatabaseError, IntegrityError) as e:
                        raise SyncError(
                            f"Database error saving message {mid}: {e}"
                        ) from e

            # Only reached if the entire transaction committed cleanly
            if successfully_saved:
                db.mark_gmail_index_synced(successfully_saved)

            return len(successfully_saved)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor_instance:
            future_to_id = {
                executor_instance.submit(thread_worker, msg_id): msg_id
                for msg_id in all_message_ids
            }

            pending_batch = []   # list of (message_id, msg) ready to write
            db_error = None

            for future in concurrent.futures.as_completed(future_to_id):
                if check_shutdown and check_shutdown():
                    continue

                message_id = future_to_id[future]
                processed_count += 1

                try:
                    if future.cancelled():
                        continue
                    mid, msg = future.result()
                    if msg is not None:
                        pending_batch.append((mid, msg))

                    # Flush batch when it reaches the target size
                    if len(pending_batch) >= DB_WRITE_BATCH_SIZE:
                        total_synced_count += flush_batch(pending_batch)
                        pending_batch = []
                        logging.info(
                            f"STATUS: Saving to database… ({total_synced_count} of {len(all_message_ids)})"
                        )

                    if (
                        processed_count % PROGRESS_LOG_INTERVAL == 0
                        or processed_count == len(all_message_ids)
                    ):
                        logging.info(
                            f"Processed {processed_count}/{len(all_message_ids)} messages "
                            f"({total_synced_count + len(pending_batch)} saved)..."
                        )

                except concurrent.futures.CancelledError:
                    pass
                except SyncError as exc:
                    logging.error(f"Database error for message {message_id}: {exc}. Stopping sync.")
                    db_error = exc
                    for f in future_to_id:
                        f.cancel()
                    break
                except Exception as exc:
                    logging.error(f"Unexpected error processing {message_id}: {exc}")

            # Flush any remaining messages
            if pending_batch and db_error is None:
                try:
                    total_synced_count += flush_batch(pending_batch)
                except SyncError as exc:
                    db_error = exc

            if db_error is not None:
                raise db_error

        if check_shutdown and check_shutdown():
            logging.info("STATUS: Stopped — sync interrupted")
            logging.info("Sync process was interrupted. Partial results saved.")
        else:
            logging.info(
                f"STATUS: Done — {total_synced_count} message{'s' if total_synced_count != 1 else ''} synced"
            )
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
        gmail_message_ids, _ = get_message_ids_from_gmail(
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
        except IntegrityError as e:
            logging.error(
                f"Could not process message {message_id} due to integrity error: {str(e)}"
            )
    except InterruptedError:
        logging.info(f"Message fetch for {message_id} was interrupted")
    except Exception as e:
        logging.error(f"Failed to fetch message {message_id}: {str(e)}")
