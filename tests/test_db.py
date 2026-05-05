"""Tests for database functionality."""

import pytest
from datetime import datetime

from peewee import TextField
from playhouse.sqlite_ext import SqliteDatabase

from gmail_to_sqlite.db import database_proxy, Message, create_message, get_message_ids_missing_raw


@pytest.fixture
def in_memory_db():
    """Set up an in-memory SQLite database for testing."""
    from gmail_to_sqlite.db import SyncState
    db = SqliteDatabase(":memory:")
    database_proxy.initialize(db)
    db.create_tables([Message, SyncState])
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


# ---------------------------------------------------------------------------
# Task 4.3: Unit tests for DB layer — raw, get_message_ids_missing_raw
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
    msg.size = overrides.get("size", 1024)
    msg.timestamp = overrides.get("timestamp", datetime(2024, 1, 1, 12, 0, 0))
    msg.is_read = overrides.get("is_read", False)
    msg.is_outgoing = overrides.get("is_outgoing", False)
    return msg
