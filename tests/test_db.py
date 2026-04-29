"""Tests for database functionality."""

import pytest
from datetime import datetime

from peewee import AutoField, BlobField, ForeignKeyField, IntegerField, TextField
from playhouse.sqlite_ext import SqliteDatabase

from gmail_to_sqlite.db import database_proxy, Attachment, Message, SchemaVersion
from gmail_to_sqlite.message import Attachment as AttachmentData


@pytest.fixture
def in_memory_db():
    """Set up an in-memory SQLite database for testing."""
    db = SqliteDatabase(":memory:")
    database_proxy.initialize(db)
    db.create_tables([Message, SchemaVersion, Attachment])
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
        body_html=None,
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

    # --- Task 6.1: body_html field is nullable ---

    def test_message_model_has_nullable_body_html(self):
        """Test that the Message model has a body_html field that is nullable."""
        # Verify the field exists on the model
        assert hasattr(Message, "body_html"), "Message model must have a body_html field"

        # Retrieve the actual field descriptor from peewee's _meta
        field = Message._meta.fields.get("body_html")
        assert field is not None, "body_html must be a declared field on Message"
        assert isinstance(field, TextField), "body_html must be a TextField"
        assert field.null is True, "body_html must be nullable (null=True)"

    # --- Task 6.2: Save and retrieve a message with non-None body_html ---

    def test_save_and_retrieve_message_with_body_html(self, in_memory_db):
        """Test saving a message with a non-None body_html and retrieving it."""
        html_content = "<html><body><p>Hello, world!</p></body></html>"
        kwargs = _make_message_kwargs(body_html=html_content)
        Message.create(**kwargs)

        retrieved = Message.get(Message.message_id == "msg-001")
        assert retrieved.body_html == html_content

    # --- Task 6.3: Save and retrieve a message with body_html=None ---

    def test_save_and_retrieve_message_with_body_html_none(self, in_memory_db):
        """Test saving a message with body_html=None and retrieving it."""
        kwargs = _make_message_kwargs(body_html=None)
        Message.create(**kwargs)

        retrieved = Message.get(Message.message_id == "msg-001")
        assert retrieved.body_html is None


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
