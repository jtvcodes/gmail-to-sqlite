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
        db.create_tables([Message, Attachment], safe=True)

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
