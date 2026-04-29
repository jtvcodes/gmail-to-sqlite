"""Property-based tests for raw-body-storage — parser and DB layer.

Properties 1–3 and 6–7 from the raw-body-storage spec.
"""

import base64
import contextlib
import uuid
from datetime import datetime

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from playhouse.sqlite_ext import SqliteDatabase

from gmail_to_sqlite.db import database_proxy, Message, SchemaVersion, Attachment as DbAttachment, create_message, create_attachments
from gmail_to_sqlite.message import Message as GmailMessage, Attachment

# ---------------------------------------------------------------------------
# In-memory DB context manager (used inside @given tests)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def fresh_db():
    """Context manager that provides a fresh in-memory SQLite database."""
    db = SqliteDatabase(":memory:")
    database_proxy.initialize(db)
    db.create_tables([Message, SchemaVersion, DbAttachment])
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_html_payload(html_content: str) -> dict:
    """Build a minimal Gmail API payload dict with a text/html part."""
    encoded = base64.urlsafe_b64encode(html_content.encode("utf-8")).decode("ascii")
    return {
        "id": "msg-prop-test",
        "threadId": "thread-prop-test",
        "sizeEstimate": len(html_content),
        "internalDate": "1700000000000",
        "labelIds": [],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Test"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(b"plain text").decode("ascii")
                    },
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": encoded},
                },
            ],
        },
    }


def _make_stub_message(body_html, message_id=None):
    """Return a minimal stub object compatible with create_message."""

    class _Stub:
        pass

    stub = _Stub()
    stub.id = message_id or str(uuid.uuid4())
    stub.thread_id = "thread-001"
    stub.sender = {"name": "Alice", "email": "alice@example.com"}
    stub.recipients = {"to": [], "cc": [], "bcc": []}
    stub.labels = []
    stub.subject = "Test"
    stub.body = "plain text"
    stub.body_html = body_html
    stub.size = 100
    stub.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    stub.is_read = False
    stub.is_outgoing = False
    stub.is_deleted = False
    return stub


# ---------------------------------------------------------------------------
# Property 1 — HTML extraction round-trip
# Validates: Requirements 1.1, 5.1
# ---------------------------------------------------------------------------


@given(html_content=st.text())
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_1_html_extraction_round_trip(html_content):
    """Feature: raw-body-storage, Property 1: HTML extraction round-trip

    For any text string encoded as base64url in a text/html payload part,
    Message.from_raw produces body_html equal to the original string.

    **Validates: Requirements 1.1, 5.1**
    """
    raw = _make_html_payload(html_content)
    msg = GmailMessage.from_raw(raw, labels={})
    assert msg.body_html == html_content, (
        f"Expected body_html={html_content!r}, got {msg.body_html!r}"
    )


# ---------------------------------------------------------------------------
# Property 2 — Storage round-trip
# Validates: Requirements 2.2, 2.3, 5.2
# ---------------------------------------------------------------------------


@given(body_html=st.one_of(st.none(), st.text()))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_2_storage_round_trip(body_html):
    """Feature: raw-body-storage, Property 2: Storage round-trip

    For any body_html value (string or None), saving and retrieving a message
    returns the same value.

    **Validates: Requirements 2.2, 2.3, 5.2**
    """
    with fresh_db():
        stub = _make_stub_message(body_html)
        create_message(stub)

        retrieved = Message.get(Message.message_id == stub.id)
        assert retrieved.body_html == body_html, (
            f"Expected body_html={body_html!r}, got {retrieved.body_html!r}"
        )


# ---------------------------------------------------------------------------
# Property 3 — Upsert updates body_html
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------


@given(
    first_html=st.one_of(st.none(), st.text()),
    second_html=st.one_of(st.none(), st.text()),
)
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_3_upsert_updates_body_html(first_html, second_html):
    """Feature: raw-body-storage, Property 3: Upsert updates body_html

    For any two body_html values, upserting with the second value results in
    the database containing the second value.

    **Validates: Requirements 2.4**
    """
    with fresh_db():
        message_id = str(uuid.uuid4())

        # Insert with first value
        stub1 = _make_stub_message(first_html, message_id=message_id)
        create_message(stub1)

        # Upsert with second value
        stub2 = _make_stub_message(second_html, message_id=message_id)
        create_message(stub2)

        retrieved = Message.get(Message.message_id == message_id)
        assert retrieved.body_html == second_html, (
            f"After upsert, expected body_html={second_html!r}, got {retrieved.body_html!r}"
        )


# ---------------------------------------------------------------------------
# Helpers for attachment tests
# ---------------------------------------------------------------------------


def _make_multipart_payload_with_attachments(attachment_specs: list) -> dict:
    """Build a minimal Gmail API payload dict with one or more attachment parts.

    Each spec is a dict with keys: mime_type, filename, size, attachment_id.
    The parts list always starts with a text/plain body part so the message
    parses cleanly, followed by one part per attachment spec.
    """
    parts = [
        {
            "mimeType": "text/plain",
            "body": {
                "data": base64.urlsafe_b64encode(b"plain text").decode("ascii"),
                "size": 10,
            },
        }
    ]

    for spec in attachment_specs:
        part: dict = {
            "mimeType": spec["mime_type"],
            "body": {
                "size": spec["size"],
            },
            "headers": [],
        }
        if spec["filename"] is not None:
            part["headers"].append(
                {
                    "name": "Content-Disposition",
                    "value": f'attachment; filename="{spec["filename"]}"',
                }
            )
        if spec["attachment_id"] is not None:
            part["body"]["attachmentId"] = spec["attachment_id"]
        parts.append(part)

    return {
        "id": "msg-attach-test",
        "threadId": "thread-attach-test",
        "sizeEstimate": 100,
        "internalDate": "1700000000000",
        "labelIds": [],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Test with attachments"},
            ],
            "parts": parts,
        },
    }


# Strategy for a single attachment spec dict
_attachment_spec_st = st.fixed_dictionaries(
    {
        "mime_type": st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=1,
        ).filter(lambda s: s not in ("text/plain", "text/html")),
        "filename": st.one_of(st.none(), st.text(min_size=1)),
        "size": st.integers(min_value=0, max_value=10_000_000),
        "attachment_id": st.one_of(st.none(), st.text(min_size=1)),
    }
)


# ---------------------------------------------------------------------------
# Property 6 — Attachment extraction completeness
# Validates: Requirements 6.1, 6.3
# ---------------------------------------------------------------------------


@given(attachment_specs=st.lists(_attachment_spec_st, min_size=1, max_size=10))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_6_attachment_extraction_completeness(attachment_specs):
    """Feature: raw-body-storage, Property 6: Attachment extraction completeness

    For any multipart payload with one or more attachment parts,
    Message.from_raw produces an attachments list with one entry per part,
    each having the correct filename, mime_type, size, and attachment_id.

    **Validates: Requirements 6.1, 6.3**
    """
    raw = _make_multipart_payload_with_attachments(attachment_specs)
    msg = GmailMessage.from_raw(raw, labels={})

    assert len(msg.attachments) == len(attachment_specs), (
        f"Expected {len(attachment_specs)} attachments, got {len(msg.attachments)}"
    )

    for i, (attachment, spec) in enumerate(zip(msg.attachments, attachment_specs)):
        assert attachment.mime_type == spec["mime_type"], (
            f"Attachment {i}: expected mime_type={spec['mime_type']!r}, "
            f"got {attachment.mime_type!r}"
        )
        assert attachment.size == spec["size"], (
            f"Attachment {i}: expected size={spec['size']}, got {attachment.size}"
        )
        assert attachment.filename == spec["filename"], (
            f"Attachment {i}: expected filename={spec['filename']!r}, "
            f"got {attachment.filename!r}"
        )
        assert attachment.attachment_id == spec["attachment_id"], (
            f"Attachment {i}: expected attachment_id={spec['attachment_id']!r}, "
            f"got {attachment.attachment_id!r}"
        )


# ---------------------------------------------------------------------------
# Property 7 — Attachment storage round-trip
# Validates: Requirements 7.2
# ---------------------------------------------------------------------------

# Strategy for a single Attachment dataclass instance
_attachment_st = st.builds(
    Attachment,
    filename=st.one_of(st.none(), st.text()),
    mime_type=st.text(min_size=1),
    size=st.integers(min_value=0, max_value=10_000_000),
    data=st.one_of(st.none(), st.binary()),
    attachment_id=st.one_of(st.none(), st.text()),
)


@given(attachments=st.lists(_attachment_st, min_size=0, max_size=10))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_7_attachment_storage_round_trip(attachments):
    """Feature: raw-body-storage, Property 7: Attachment storage round-trip

    For any list of Attachment objects saved via create_attachments, querying
    the DB returns rows with matching field values.

    **Validates: Requirements 7.2**
    """
    with fresh_db():
        # We need a parent message row for the FK constraint
        message_id = str(uuid.uuid4())
        stub = _make_stub_message(body_html=None, message_id=message_id)
        stub.attachments = []  # don't insert attachments via create_message
        create_message(stub)

        # Now store the generated attachments
        create_attachments(message_id, attachments)

        # Query back
        rows = list(
            DbAttachment.select().where(DbAttachment.message_id == message_id)
        )

        assert len(rows) == len(attachments), (
            f"Expected {len(attachments)} rows, got {len(rows)}"
        )

        for i, (row, original) in enumerate(zip(rows, attachments)):
            assert row.filename == original.filename, (
                f"Row {i}: expected filename={original.filename!r}, got {row.filename!r}"
            )
            assert row.mime_type == original.mime_type, (
                f"Row {i}: expected mime_type={original.mime_type!r}, got {row.mime_type!r}"
            )
            assert row.size == original.size, (
                f"Row {i}: expected size={original.size}, got {row.size}"
            )
            assert row.attachment_id == original.attachment_id, (
                f"Row {i}: expected attachment_id={original.attachment_id!r}, "
                f"got {row.attachment_id!r}"
            )
            # Compare data: BlobField returns bytes or None
            stored_data = bytes(row.data) if row.data is not None else None
            assert stored_data == original.data, (
                f"Row {i}: expected data={original.data!r}, got {stored_data!r}"
            )
