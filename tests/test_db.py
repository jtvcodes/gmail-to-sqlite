"""Tests for database functionality."""

import pytest
from datetime import datetime

from peewee import AutoField, BlobField, ForeignKeyField, IntegerField, TextField
from playhouse.sqlite_ext import SqliteDatabase

from gmail_to_sqlite.db import database_proxy, Attachment, Message, create_message, get_message_ids_missing_raw
from gmail_to_sqlite.message import Attachment as AttachmentData


@pytest.fixture
def in_memory_db():
    """Set up an in-memory SQLite database for testing."""
    db = SqliteDatabase(":memory:")
    database_proxy.initialize(db)
    db.create_tables([Message, Attachment])
    yield db
    db.close()


def _make_message_kwargs(**overrides):
    """Return a dict of minimal valid Message field values."""
    defaults = dict(
        message_id="msg-001",
        thread_id="thread-001",
        sender={"name": "Alice", "email": "alice@example.com"},
        recipients=[{"name": "Bob", "email": "bob@example.com"}],
        labels=["INBOX"],
        subject="Hello",
        body="Plain text body",
        raw=None,
        received_date=None,
        size=1024,
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        is_read=False,
        is_outgoing=False,
        is_deleted=False,
        last_indexed=datetime(2024, 1, 1, 12, 0, 0),
    )
    defaults.update(overrides)
    return defaults


class TestDatabase:
    """Test database operations."""

    def test_initialize_database(self, temp_dir):
        """Test database initialization."""
        from gmail_to_sqlite.db import init
        db_path = str(temp_dir)
        db = init(db_path)
        assert db is not None
        db.close()

    def test_message_model(self):
        """Test Message model creation."""
        # Test that the model exists and has required fields
        assert Message is not None
        assert hasattr(Message, "message_id")
        assert hasattr(Message, "subject")
        assert hasattr(Message, "thread_id")
        assert hasattr(Message, "sender")
        assert hasattr(Message, "recipients")

    # --- Task 6.1: raw field is nullable ---

    def test_message_model_has_nullable_raw(self):
        """Test that the Message model has a raw field that is nullable."""
        # Verify the field exists on the model
        assert hasattr(Message, "raw"), "Message model must have a raw field"

        # Retrieve the actual field descriptor from peewee's _meta
        field = Message._meta.fields.get("raw")
        assert field is not None, "raw must be a declared field on Message"
        assert isinstance(field, TextField), "raw must be a TextField"
        assert field.null is True, "raw must be nullable (null=True)"

    # --- Task 6.2: Save and retrieve a message with non-None raw ---

    def test_save_and_retrieve_message_with_raw(self, in_memory_db):
        """Test saving a message with a non-None raw and retrieving it."""
        raw_content = "From: sender@example.com\r\nTo: recipient@example.com\r\n\r\nHello"
        kwargs = _make_message_kwargs(raw=raw_content)
        Message.create(**kwargs)

        retrieved = Message.get(Message.message_id == "msg-001")
        assert retrieved.raw == raw_content

    # --- Task 6.3: Save and retrieve a message with raw=None ---

    def test_save_and_retrieve_message_with_raw_none(self, in_memory_db):
        """Test saving a message with raw=None and retrieving it."""
        kwargs = _make_message_kwargs(raw=None)
        Message.create(**kwargs)

        retrieved = Message.get(Message.message_id == "msg-001")
        assert retrieved.raw is None


class TestAttachmentDatabase:
    """Test database operations for the Attachment model and create_attachments function."""

    # --- Task 15.1: Attachment model has all required fields with correct types ---

    def test_attachment_model_has_all_required_fields(self):
        """Test that the Attachment model has all required fields with correct types and nullability."""
        fields = Attachment._meta.fields

        # id: AutoField (primary key)
        assert "id" in fields, "Attachment must have an 'id' field"
        assert isinstance(fields["id"], AutoField), "id must be an AutoField"

        # message_id: ForeignKeyField
        assert "message_id" in fields, "Attachment must have a 'message_id' field"
        assert isinstance(fields["message_id"], ForeignKeyField), (
            "message_id must be a ForeignKeyField"
        )

        # filename: TextField, nullable
        assert "filename" in fields, "Attachment must have a 'filename' field"
        assert isinstance(fields["filename"], TextField), "filename must be a TextField"
        assert fields["filename"].null is True, "filename must be nullable (null=True)"

        # mime_type: TextField, not nullable
        assert "mime_type" in fields, "Attachment must have a 'mime_type' field"
        assert isinstance(fields["mime_type"], TextField), "mime_type must be a TextField"
        assert fields["mime_type"].null is False, "mime_type must NOT be nullable"

        # size: IntegerField, default 0
        assert "size" in fields, "Attachment must have a 'size' field"
        assert isinstance(fields["size"], IntegerField), "size must be an IntegerField"
        assert fields["size"].default == 0, "size must have default=0"

        # data: BlobField, nullable
        assert "data" in fields, "Attachment must have a 'data' field"
        assert isinstance(fields["data"], BlobField), "data must be a BlobField"
        assert fields["data"].null is True, "data must be nullable (null=True)"

        # attachment_id: TextField, nullable
        assert "attachment_id" in fields, "Attachment must have an 'attachment_id' field"
        assert isinstance(fields["attachment_id"], TextField), (
            "attachment_id must be a TextField"
        )
        assert fields["attachment_id"].null is True, (
            "attachment_id must be nullable (null=True)"
        )

    # --- Task 15.2: Save attachments for a message and retrieve them ---

    def test_save_and_retrieve_attachments(self, in_memory_db):
        """Test saving attachments for a message and retrieving them; assert all field values match."""
        from gmail_to_sqlite.db import create_attachments

        # Create a parent Message row first
        Message.create(**_make_message_kwargs(message_id="msg-attach-001"))

        attachment_data = [
            AttachmentData(
                filename="report.pdf",
                mime_type="application/pdf",
                size=2048,
                data=b"PDF binary content",
                attachment_id=None,
            ),
            AttachmentData(
                filename="photo.jpg",
                mime_type="image/jpeg",
                size=512,
                data=b"\xff\xd8\xff",
                attachment_id="gmail-attach-id-123",
            ),
        ]

        create_attachments("msg-attach-001", attachment_data)

        rows = list(
            Attachment.select().where(Attachment.message_id == "msg-attach-001")
        )
        assert len(rows) == 2

        # Sort by filename for deterministic comparison
        rows.sort(key=lambda r: r.filename or "")

        assert rows[0].filename == "photo.jpg"
        assert rows[0].mime_type == "image/jpeg"
        assert rows[0].size == 512
        assert bytes(rows[0].data) == b"\xff\xd8\xff"
        assert rows[0].attachment_id == "gmail-attach-id-123"

        assert rows[1].filename == "report.pdf"
        assert rows[1].mime_type == "application/pdf"
        assert rows[1].size == 2048
        assert bytes(rows[1].data) == b"PDF binary content"
        assert rows[1].attachment_id is None

    # --- Task 15.3: Re-syncing a message replaces its attachments ---

    def test_resyncing_message_replaces_attachments(self, in_memory_db):
        """Test that calling create_attachments twice replaces the first set with the second."""
        from gmail_to_sqlite.db import create_attachments

        Message.create(**_make_message_kwargs(message_id="msg-resync-001"))

        first_set = [
            AttachmentData(
                filename="old_file.txt",
                mime_type="text/plain",
                size=100,
                data=b"old content",
                attachment_id=None,
            ),
        ]
        create_attachments("msg-resync-001", first_set)

        # Confirm first set is present
        assert Attachment.select().where(Attachment.message_id == "msg-resync-001").count() == 1

        second_set = [
            AttachmentData(
                filename="new_file_a.pdf",
                mime_type="application/pdf",
                size=300,
                data=b"new pdf content",
                attachment_id=None,
            ),
            AttachmentData(
                filename="new_file_b.png",
                mime_type="image/png",
                size=400,
                data=b"new png content",
                attachment_id=None,
            ),
        ]
        create_attachments("msg-resync-001", second_set)

        rows = list(
            Attachment.select().where(Attachment.message_id == "msg-resync-001")
        )
        assert len(rows) == 2, "Only the second set of attachments should be present"

        filenames = {r.filename for r in rows}
        assert filenames == {"new_file_a.pdf", "new_file_b.png"}, (
            "Only filenames from the second set should be present"
        )
        assert "old_file.txt" not in filenames, (
            "Filename from the first set must not be present after re-sync"
        )

    # --- Task 15.4: Save attachment with data=None; assert data column is NULL ---

    def test_save_attachment_with_null_data(self, in_memory_db):
        """Test saving an attachment with data=None and retrieving it; assert data column is NULL."""
        from gmail_to_sqlite.db import create_attachments

        Message.create(**_make_message_kwargs(message_id="msg-null-data-001"))

        attachment_data = [
            AttachmentData(
                filename="large_attachment.zip",
                mime_type="application/zip",
                size=10_000_000,
                data=None,
                attachment_id="gmail-large-attach-id-456",
            ),
        ]

        create_attachments("msg-null-data-001", attachment_data)

        row = Attachment.get(Attachment.message_id == "msg-null-data-001")
        assert row.data is None, "data column must be NULL when attachment data is None"
        assert row.attachment_id == "gmail-large-attach-id-456"
        assert row.filename == "large_attachment.zip"
        assert row.mime_type == "application/zip"
        assert row.size == 10_000_000


# ---------------------------------------------------------------------------
# Task 4.3: Unit tests for DB layer — raw, received_date, get_message_ids_missing_raw
# Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 10.1
# ---------------------------------------------------------------------------


def _make_msg_object(**overrides):
    """Return a minimal gmail_to_sqlite.message.Message-like object for create_message."""
    from gmail_to_sqlite.message import Message as MsgClass

    msg = MsgClass()
    msg.id = overrides.get("id", "msg-raw-001")
    msg.thread_id = overrides.get("thread_id", "thread-raw-001")
    msg.sender = overrides.get("sender", {"name": "Alice", "email": "alice@example.com"})
    msg.recipients = overrides.get("recipients", {"to": [{"name": "Bob", "email": "bob@example.com"}]})
    msg.labels = overrides.get("labels", ["INBOX"])
    msg.subject = overrides.get("subject", "Test Subject")
    msg.body = overrides.get("body", "Plain text body")
    msg.raw = overrides.get("raw", None)
    msg.received_date = overrides.get("received_date", None)
    msg.size = overrides.get("size", 1024)
    msg.timestamp = overrides.get("timestamp", datetime(2024, 1, 1, 12, 0, 0))
    msg.is_read = overrides.get("is_read", False)
    msg.is_outgoing = overrides.get("is_outgoing", False)
    msg.attachments = overrides.get("attachments", [])
    return msg


class TestRawAndReceivedDate:
    """Tests for raw column, received_date column, and get_message_ids_missing_raw."""

    def test_create_message_writes_raw_column(self, in_memory_db):
        """Test that create_message writes the raw attribute to the raw column."""
        raw_content = "From: sender@example.com\r\nTo: recipient@example.com\r\n\r\nHello"
        msg = _make_msg_object(raw=raw_content)
        create_message(msg)

        stored = Message.get(Message.message_id == "msg-raw-001")
        assert stored.raw == raw_content

    def test_create_message_writes_raw_column_none(self, in_memory_db):
        """Test that create_message stores NULL when raw is None."""
        msg = _make_msg_object(raw=None)
        create_message(msg)

        stored = Message.get(Message.message_id == "msg-raw-001")
        assert stored.raw is None

    def test_create_message_writes_received_date_column(self, in_memory_db):
        """Test that create_message writes the received_date attribute to the received_date column."""
        received = datetime(2024, 6, 15, 10, 30, 0)
        msg = _make_msg_object(received_date=received)
        create_message(msg)

        stored = Message.get(Message.message_id == "msg-raw-001")
        # Peewee may return a datetime; compare as datetime
        assert stored.received_date is not None
        # Compare truncated to seconds
        assert stored.received_date.replace(microsecond=0) == received.replace(microsecond=0)

    def test_create_message_writes_received_date_column_none(self, in_memory_db):
        """Test that create_message stores NULL when received_date is None."""
        msg = _make_msg_object(received_date=None)
        create_message(msg)

        stored = Message.get(Message.message_id == "msg-raw-001")
        assert stored.received_date is None

    def test_upsert_updates_raw_column(self, in_memory_db):
        """Test that calling create_message twice (upsert) updates the raw column."""
        msg1 = _make_msg_object(raw="original raw content")
        create_message(msg1)

        msg2 = _make_msg_object(raw="updated raw content")
        create_message(msg2)

        stored = Message.get(Message.message_id == "msg-raw-001")
        assert stored.raw == "updated raw content"

    def test_upsert_updates_received_date_column(self, in_memory_db):
        """Test that calling create_message twice (upsert) updates the received_date column."""
        original_date = datetime(2024, 1, 1, 10, 0, 0)
        updated_date = datetime(2024, 6, 15, 10, 30, 0)

        msg1 = _make_msg_object(received_date=original_date)
        create_message(msg1)

        msg2 = _make_msg_object(received_date=updated_date)
        create_message(msg2)

        stored = Message.get(Message.message_id == "msg-raw-001")
        assert stored.received_date is not None
        assert stored.received_date.replace(microsecond=0) == updated_date.replace(microsecond=0)

    def test_upsert_updates_both_raw_and_received_date(self, in_memory_db):
        """Test that upsert updates both raw and received_date simultaneously."""
        msg1 = _make_msg_object(
            raw="first raw",
            received_date=datetime(2024, 1, 1, 10, 0, 0),
        )
        create_message(msg1)

        new_raw = "second raw"
        new_date = datetime(2024, 12, 31, 23, 59, 59)
        msg2 = _make_msg_object(raw=new_raw, received_date=new_date)
        create_message(msg2)

        stored = Message.get(Message.message_id == "msg-raw-001")
        assert stored.raw == new_raw
        assert stored.received_date.replace(microsecond=0) == new_date.replace(microsecond=0)

    def test_get_message_ids_missing_raw_returns_correct_ids(self, in_memory_db):
        """Test that get_message_ids_missing_raw returns IDs where raw is NULL."""
        # Insert messages: some with raw, some without
        msg_with_raw = _make_msg_object(id="msg-has-raw", raw="some raw content")
        msg_without_raw_1 = _make_msg_object(id="msg-no-raw-1", raw=None)
        msg_without_raw_2 = _make_msg_object(id="msg-no-raw-2", raw=None)

        create_message(msg_with_raw)
        create_message(msg_without_raw_1)
        create_message(msg_without_raw_2)

        missing = get_message_ids_missing_raw()
        assert set(missing) == {"msg-no-raw-1", "msg-no-raw-2"}
        assert "msg-has-raw" not in missing

    def test_get_message_ids_missing_raw_empty_when_all_have_raw(self, in_memory_db):
        """Test that get_message_ids_missing_raw returns empty list when all messages have raw."""
        msg1 = _make_msg_object(id="msg-001", raw="raw content 1")
        msg2 = _make_msg_object(id="msg-002", raw="raw content 2")
        create_message(msg1)
        create_message(msg2)

        missing = get_message_ids_missing_raw()
        assert missing == []

    def test_get_message_ids_missing_raw_all_missing(self, in_memory_db):
        """Test that get_message_ids_missing_raw returns all IDs when all messages have NULL raw."""
        msg1 = _make_msg_object(id="msg-001", raw=None)
        msg2 = _make_msg_object(id="msg-002", raw=None)
        create_message(msg1)
        create_message(msg2)

        missing = get_message_ids_missing_raw()
        assert set(missing) == {"msg-001", "msg-002"}
