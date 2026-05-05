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

from gmail_to_sqlite.db import database_proxy, Message, create_message
from gmail_to_sqlite.message import Message as GmailMessage

# ---------------------------------------------------------------------------
# In-memory DB context manager (used inside @given tests)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def fresh_db():
    """Context manager that provides a fresh in-memory SQLite database."""
    db = SqliteDatabase(":memory:")
    database_proxy.initialize(db)
    db.create_tables([Message])
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
    """Return a minimal stub object compatible with create_message.

    Note: body_html is kept as a parameter name for backward compatibility
    but the value is stored in the raw field (body_html was replaced by raw).
    """

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
    stub.raw = body_html  # raw replaces body_html
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
    # body_html is still set by from_raw via _extract_html_body
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

    For any raw value (string or None), saving and retrieving a message
    returns the same value.

    **Validates: Requirements 2.2, 2.3, 5.2**
    """
    with fresh_db():
        stub = _make_stub_message(body_html)
        create_message(stub)

        retrieved = Message.get(Message.message_id == stub.id)
        assert retrieved.raw == body_html, (
            f"Expected raw={body_html!r}, got {retrieved.raw!r}"
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
    """Feature: raw-body-storage, Property 3: Upsert updates raw

    For any two raw values, upserting with the second value results in
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
        assert retrieved.raw == second_html, (
            f"After upsert, expected raw={second_html!r}, got {retrieved.raw!r}"
        )

