import logging
from datetime import datetime
from typing import Any, List, Optional

from peewee import (
    AutoField,
    BlobField,
    BooleanField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    Model,
    Proxy,
    TextField,
    SQL,
)
from playhouse.sqlite_ext import JSONField, SqliteDatabase

from .constants import DATABASE_FILE_NAME

database_proxy = Proxy()


class DatabaseError(Exception):
    """Custom exception for database-related errors."""

    pass


class GmailIndex(Model):
    """Lightweight index of every known Gmail message ID.

    Populated quickly from messages.list without downloading content.
    ``synced`` is set to True once the full message has been downloaded
    and stored in the ``messages`` table.
    """

    message_id = TextField(primary_key=True)
    synced = BooleanField(default=False)
    last_sync_date = DateTimeField(null=True)

    class Meta:
        database = database_proxy
        table_name = "gmail_index"


class Message(Model):
    """Represents an email message."""

    message_id = TextField(unique=True)
    thread_id = TextField()
    sender = JSONField()
    recipients = JSONField()
    labels = JSONField()
    subject = TextField(null=True)
    body = TextField(null=True)
    raw = TextField(null=True)
    received_date = DateTimeField(null=True)
    size = IntegerField()
    timestamp = DateTimeField(null=True)
    is_read = BooleanField()
    is_outgoing = BooleanField()
    is_deleted = BooleanField(default=False)
    last_indexed = DateTimeField()

    class Meta:
        database = database_proxy
        table_name = "messages"


class Attachment(Model):
    """Represents an email attachment linked to a message."""

    id = AutoField()
    message_id = ForeignKeyField(
        Message,
        backref="attachments",
        column_name="message_id",
        field="message_id",
    )
    filename = TextField(null=True)
    mime_type = TextField()
    size = IntegerField(default=0)
    data = BlobField(null=True)
    attachment_id = TextField(null=True)
    content_id = TextField(null=True)

    class Meta:
        database = database_proxy
        table_name = "attachments"


class SyncState(Model):
    """Stores persistent key/value sync state (e.g. the last Gmail historyId)."""

    key = TextField(primary_key=True)
    value = TextField()

    class Meta:
        database = database_proxy
        table_name = "sync_state"


def init(data_dir: str, enable_logging: bool = False) -> SqliteDatabase:
    """
    Initialize the database for the given data_dir.

    Creates the messages and attachments tables if they don't already exist.

    Args:
        data_dir (str): The path where to store the data.
        enable_logging (bool, optional): Whether to enable logging. Defaults to False.

    Returns:
        SqliteDatabase: The initialized database object.

    Raises:
        DatabaseError: If database initialization fails.
    """
    try:
        db_path = f"{data_dir}/{DATABASE_FILE_NAME}"
        db = SqliteDatabase(db_path)
        database_proxy.initialize(db)
        db.create_tables([Message, Attachment, SyncState, GmailIndex], safe=True)

        if enable_logging:
            logger = logging.getLogger("peewee")
            logger.setLevel(logging.DEBUG)
            logger.addHandler(logging.StreamHandler())

        return db
    except Exception as e:
        raise DatabaseError(f"Failed to initialize database: {e}")


def create_attachments(message_id: str, attachments: List) -> None:
    """
    Replaces all attachment rows for a message with the provided list.

    Deletes any existing attachment rows for ``message_id`` first, then
    bulk-inserts the new rows.  This makes the operation idempotent for
    re-syncs.

    Args:
        message_id (str): The message ID whose attachments are being stored.
        attachments (List): List of ``gmail_to_sqlite.message.Attachment``
            dataclass instances.

    Raises:
        DatabaseError: If the delete or insert operation fails.
    """
    try:
        Attachment.delete().where(Attachment.message_id == message_id).execute()
        if attachments:
            rows = [
                {
                    "message_id": message_id,
                    "filename": a.filename,
                    "mime_type": a.mime_type,
                    "size": a.size,
                    "data": a.data,
                    "attachment_id": a.attachment_id,
                    "content_id": a.content_id,
                }
                for a in attachments
            ]
            Attachment.insert_many(rows).execute()
    except Exception as e:
        raise DatabaseError(
            f"Failed to save attachments for message {message_id}: {e}"
        )


def create_message(msg: Any) -> None:
    """
    Saves a message to the database with conflict resolution.

    Args:
        msg: The message object to save (from message.Message class).

    Raises:
        DatabaseError: If the message cannot be saved to the database.
    """
    try:
        last_indexed = datetime.now()
        Message.insert(
            message_id=msg.id,
            thread_id=msg.thread_id,
            sender=msg.sender,
            recipients=msg.recipients,
            labels=msg.labels,
            subject=msg.subject,
            body=msg.body,
            raw=msg.raw,
            received_date=msg.received_date,
            size=msg.size,
            timestamp=msg.timestamp,
            is_read=msg.is_read,
            is_outgoing=msg.is_outgoing,
            is_deleted=False,
            last_indexed=last_indexed,
        ).on_conflict(
            conflict_target=[Message.message_id],
            update={
                Message.is_read: msg.is_read,
                Message.last_indexed: last_indexed,
                Message.labels: msg.labels,
                Message.is_deleted: False,
                Message.raw: msg.raw,
                Message.received_date: msg.received_date,
            },
        ).execute()
        create_attachments(msg.id, getattr(msg, "attachments", []))
    except Exception as e:
        raise DatabaseError(f"Failed to save message {msg.id}: {e}")


def last_indexed() -> Optional[datetime]:
    """
    Returns the timestamp of the last indexed message.

    Returns:
        Optional[datetime]: The timestamp of the last indexed message, or None if no messages exist.
    """

    msg = Message.select().order_by(Message.timestamp.desc()).first()
    if msg:
        timestamp: Optional[datetime] = msg.timestamp
        return timestamp
    else:
        return None


def first_indexed() -> Optional[datetime]:
    """
    Returns the timestamp of the first indexed message.

    Returns:
        Optional[datetime]: The timestamp of the first indexed message, or None if no messages exist.
    """

    msg = Message.select().order_by(Message.timestamp.asc()).first()
    if msg:
        timestamp: Optional[datetime] = msg.timestamp
        return timestamp
    else:
        return None


def mark_messages_as_deleted(message_ids: List[str]) -> None:
    """
    Mark messages as deleted in the database.

    Args:
        message_ids (List[str]): List of message IDs to mark as deleted.

    Raises:
        DatabaseError: If the operation fails.
    """
    if not message_ids:
        return

    try:
        # Use the SQL IN clause with proper parameter binding
        batch_size = 100
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i : i + batch_size]
            placeholders = ",".join(["?" for _ in batch])
            query = Message.update(is_deleted=True, last_indexed=datetime.now())
            query = query.where(SQL(f"message_id IN ({placeholders})", batch))
            query.execute()
    except Exception as e:
        raise DatabaseError(f"Failed to mark messages as deleted: {e}")


def get_all_message_ids() -> List[str]:
    """
    Returns all message IDs stored in the database.

    Returns:
        List[str]: List of message IDs.

    Raises:
        DatabaseError: If the query fails.
    """
    try:
        return [message.message_id for message in Message.select(Message.message_id)]
    except Exception as e:
        raise DatabaseError(f"Failed to retrieve message IDs: {e}")


def get_message_ids_missing_raw() -> List[str]:
    """
    Returns message IDs where the raw column is NULL (candidates for re-sync
    to fetch the complete RFC 2822 source).

    Returns:
        List[str]: List of message IDs with NULL raw.
    """
    try:
        return [
            message.message_id
            for message in Message.select(Message.message_id).where(
                Message.raw.is_null(True)
            )
        ]
    except Exception as e:
        raise DatabaseError(f"Failed to retrieve message IDs missing raw: {e}")


def get_deleted_message_ids() -> List[str]:
    """
    Returns all message IDs that are already marked as deleted.

    Returns:
        List[str]: List of deleted message IDs.

    Raises:
        DatabaseError: If the query fails.
    """
    try:
        return [
            message.message_id
            for message in Message.select(Message.message_id).where(
                Message.is_deleted == True  # noqa: E712
            )
        ]
    except Exception as e:
        raise DatabaseError(f"Failed to retrieve deleted message IDs: {e}")


def get_sync_state(key: str) -> Optional[str]:
    """Return the stored value for key, or None.

    Args:
        key (str): The state key to look up (e.g. "history_id").

    Returns:
        Optional[str]: The stored value, or None if not found.
    """
    try:
        row = SyncState.get_or_none(SyncState.key == key)
        return row.value if row is not None else None
    except Exception as e:
        raise DatabaseError(f"Failed to get sync state for key '{key}': {e}")


def set_sync_state(key: str, value: str) -> None:
    """Upsert key=value into sync_state.

    Args:
        key (str): The state key (e.g. "history_id").
        value (str): The value to store.

    Raises:
        DatabaseError: If the upsert fails.
    """
    try:
        SyncState.insert(key=key, value=value).on_conflict(
            conflict_target=[SyncState.key],
            update={SyncState.value: value},
        ).execute()
    except Exception as e:
        raise DatabaseError(f"Failed to set sync state for key '{key}': {e}")


def get_cached_gmail_ids() -> Optional[List[str]]:
    """Return unsynced message IDs from the gmail_index table.

    Kept for backward compatibility — delegates to get_unsynced_gmail_ids.
    """
    return get_unsynced_gmail_ids()


def set_cached_gmail_ids(message_ids: List[str]) -> None:
    """Bulk-upsert message IDs into gmail_index without marking them synced.

    Kept for backward compatibility — delegates to upsert_gmail_index.
    """
    upsert_gmail_index(message_ids)


def upsert_gmail_index(message_ids: List[str]) -> None:
    """Bulk-upsert message IDs into gmail_index, preserving existing synced state.

    New IDs are inserted with synced=False.  Existing rows are left unchanged
    so that already-synced messages keep their synced=True flag.

    Args:
        message_ids: List of Gmail message IDs to register.

    Raises:
        DatabaseError: If the operation fails.
    """
    if not message_ids:
        return
    try:
        batch_size = 500
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i:i + batch_size]
            rows = [{"message_id": mid, "synced": False, "last_sync_date": None}
                    for mid in batch]
            # INSERT OR IGNORE — don't overwrite existing rows
            GmailIndex.insert_many(rows).on_conflict_ignore().execute()
    except Exception as e:
        raise DatabaseError(f"Failed to upsert gmail_index: {e}")


def mark_gmail_index_synced(message_ids: List[str]) -> None:
    """Mark message IDs as synced in gmail_index.

    Args:
        message_ids: List of Gmail message IDs that have been fully downloaded.

    Raises:
        DatabaseError: If the operation fails.
    """
    if not message_ids:
        return
    try:
        now = datetime.now()
        batch_size = 500
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i:i + batch_size]
            placeholders = ",".join(["?" for _ in batch])
            GmailIndex.update(synced=True, last_sync_date=now).where(
                SQL(f"message_id IN ({placeholders})", batch)
            ).execute()
    except Exception as e:
        raise DatabaseError(f"Failed to mark gmail_index synced: {e}")


def mark_gmail_index_deleted(message_ids: List[str]) -> None:
    """Remove message IDs from gmail_index (they no longer exist in Gmail).

    Args:
        message_ids: List of Gmail message IDs to remove from the index.

    Raises:
        DatabaseError: If the operation fails.
    """
    if not message_ids:
        return
    try:
        batch_size = 500
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i:i + batch_size]
            placeholders = ",".join(["?" for _ in batch])
            GmailIndex.delete().where(
                SQL(f"message_id IN ({placeholders})", batch)
            ).execute()
    except Exception as e:
        raise DatabaseError(f"Failed to remove deleted IDs from gmail_index: {e}")


def get_unsynced_gmail_ids() -> List[str]:
    """Return all message IDs in gmail_index where synced=False.

    These are IDs known to exist in Gmail but not yet downloaded.

    Returns:
        List[str]: Unsynced message IDs.

    Raises:
        DatabaseError: If the query fails.
    """
    try:
        return [
            row.message_id
            for row in GmailIndex.select(GmailIndex.message_id).where(
                GmailIndex.synced == False  # noqa: E712
            )
        ]
    except Exception as e:
        raise DatabaseError(f"Failed to get unsynced gmail IDs: {e}")


def get_gmail_index_count() -> dict:
    """Return counts of total, synced, and unsynced IDs in gmail_index.

    Returns:
        dict with keys: total, synced, unsynced.
    """
    try:
        total = GmailIndex.select().count()
        synced = GmailIndex.select().where(GmailIndex.synced == True).count()  # noqa: E712
        return {"total": total, "synced": synced, "unsynced": total - synced}
    except Exception as e:
        raise DatabaseError(f"Failed to get gmail_index counts: {e}")
