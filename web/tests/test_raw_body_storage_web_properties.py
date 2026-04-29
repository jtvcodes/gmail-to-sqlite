"""Property-based tests for raw-body-storage — Web API layer.

Properties 4–5 and 8–9 from the raw-body-storage spec.
"""

import json
import os
import sqlite3
import tempfile
import uuid

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from web.server import create_app

# ---------------------------------------------------------------------------
# DB schema (mirrors web/tests/test_web_properties.py)
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE messages (
    message_id   TEXT PRIMARY KEY,
    thread_id    TEXT,
    sender       TEXT,
    recipients   TEXT,
    labels       TEXT,
    subject      TEXT,
    body         TEXT,
    body_html    TEXT,
    size         INTEGER,
    timestamp    DATETIME,
    is_read      INTEGER,
    is_outgoing  INTEGER,
    is_deleted   INTEGER,
    last_indexed DATETIME
)
"""

CREATE_ATTACHMENTS_TABLE_SQL = """
CREATE TABLE attachments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    TEXT NOT NULL REFERENCES messages(message_id),
    filename      TEXT,
    mime_type     TEXT NOT NULL,
    size          INTEGER NOT NULL DEFAULT 0,
    data          BLOB,
    attachment_id TEXT
)
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_single_message(path: str, message_id: str, body_html) -> None:
    """Create the messages table and insert one row with the given body_html."""
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            message_id,
            "thread-001",
            json.dumps({"name": "Alice", "email": "alice@example.com"}),
            json.dumps({"to": [], "cc": [], "bcc": []}),
            json.dumps([]),
            "Test Subject",
            "plain body",
            body_html,  # may be None → stored as NULL
            100,
            "2024-01-01T12:00:00",
            1,
            0,
            0,
            "2024-01-01T12:00:00",
        ),
    )
    conn.commit()
    conn.close()


def _seed_multiple_messages(path: str, body_html_values: list) -> list:
    """Create the messages table and insert one row per body_html value.

    Returns the list of inserted message_ids.
    """
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    message_ids = []
    for i, body_html in enumerate(body_html_values):
        mid = str(i)
        message_ids.append(mid)
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                mid,
                f"thread-{i}",
                json.dumps({"name": "Alice", "email": "alice@example.com"}),
                json.dumps({"to": [], "cc": [], "bcc": []}),
                json.dumps([]),
                f"Subject {i}",
                "plain body",
                body_html,
                100,
                "2024-01-01T12:00:00",
                1,
                0,
                0,
                "2024-01-01T12:00:00",
            ),
        )
    conn.commit()
    conn.close()
    return message_ids


def _make_client(db_path: str):
    """Return a Flask test client configured to use db_path."""
    flask_app = create_app(db_path=db_path)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Property 4 — Detail API returns body_html verbatim
# Validates: Requirements 4.1, 4.2, 4.3
# ---------------------------------------------------------------------------


@given(body_html=st.one_of(st.none(), st.text()))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_4_detail_api_returns_body_html_verbatim(body_html):
    """Feature: raw-body-storage, Property 4: Detail API returns body_html verbatim

    For any stored body_html value, the detail endpoint returns it unchanged.

    **Validates: Requirements 4.1, 4.2, 4.3**
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    message_id = str(uuid.uuid4())
    try:
        _seed_single_message(tmp.name, message_id, body_html)
        client = _make_client(tmp.name)

        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

        data = resp.get_json()
        assert "body_html" in data, "Response must contain 'body_html' key"
        assert data["body_html"] == body_html, (
            f"Expected body_html={body_html!r}, got {data['body_html']!r}"
        )
    finally:
        _cleanup(tmp.name)


# ---------------------------------------------------------------------------
# Property 5 — List API excludes body_html
# Validates: Requirements 4.4
# ---------------------------------------------------------------------------


@given(body_html_values=st.lists(st.one_of(st.none(), st.text()), min_size=0, max_size=10))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_5_list_api_excludes_body_html(body_html_values):
    """Feature: raw-body-storage, Property 5: List API excludes body_html

    For any set of stored messages, no item in the list response contains a
    'body_html' key.

    **Validates: Requirements 4.4**
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        _seed_multiple_messages(tmp.name, body_html_values)
        client = _make_client(tmp.name)

        resp = client.get("/api/messages?page_size=200")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

        data = resp.get_json()
        for item in data["messages"]:
            assert "body_html" not in item, (
                f"List item for message_id={item.get('message_id')!r} "
                f"must not contain 'body_html', but got keys: {list(item.keys())}"
            )
    finally:
        _cleanup(tmp.name)


# ---------------------------------------------------------------------------
# Helpers for attachment tests
# ---------------------------------------------------------------------------


def _seed_message_with_attachments(
    path: str,
    message_id: str,
    attachments: list,
) -> None:
    """Create messages + attachments tables and insert one message with attachments.

    Each item in ``attachments`` is a dict with keys:
    filename, mime_type, size, data, attachment_id.
    """
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
    conn.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            message_id,
            "thread-001",
            json.dumps({"name": "Alice", "email": "alice@example.com"}),
            json.dumps({"to": [], "cc": [], "bcc": []}),
            json.dumps([]),
            "Test Subject",
            "plain body",
            None,
            100,
            "2024-01-01T12:00:00",
            1,
            0,
            0,
            "2024-01-01T12:00:00",
        ),
    )
    for att in attachments:
        conn.execute(
            "INSERT INTO attachments (message_id, filename, mime_type, size, data, attachment_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                message_id,
                att["filename"],
                att["mime_type"],
                att["size"],
                att["data"],
                att["attachment_id"],
            ),
        )
    conn.commit()
    conn.close()


# Strategy for a single attachment dict (for web tests)
_web_attachment_st = st.fixed_dictionaries(
    {
        "filename": st.one_of(st.none(), st.text()),
        "mime_type": st.text(min_size=1),
        "size": st.integers(min_value=0, max_value=10_000_000),
        "data": st.one_of(st.none(), st.binary()),
        "attachment_id": st.one_of(st.none(), st.text(min_size=1)),
    }
)


# ---------------------------------------------------------------------------
# Property 8 — Detail API attachments array shape
# Validates: Requirements 9.1, 9.2
# ---------------------------------------------------------------------------


@given(attachments=st.lists(_web_attachment_st, min_size=0, max_size=10))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_detail_api_attachments_array_shape(attachments):
    """Feature: raw-body-storage, Property 8: Detail API attachments array shape

    For any message stored with attachments, every item in the attachments
    array of the detail response has keys filename, mime_type, size,
    attachment_id and does NOT have key data.

    **Validates: Requirements 9.1, 9.2**
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    message_id = str(uuid.uuid4())
    try:
        _seed_message_with_attachments(tmp.name, message_id, attachments)
        client = _make_client(tmp.name)

        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

        data = resp.get_json()
        assert "attachments" in data, "Response must contain 'attachments' key"
        assert isinstance(data["attachments"], list), "'attachments' must be a list"
        assert len(data["attachments"]) == len(attachments), (
            f"Expected {len(attachments)} attachments, got {len(data['attachments'])}"
        )

        required_keys = {"filename", "mime_type", "size", "attachment_id"}
        for i, item in enumerate(data["attachments"]):
            for key in required_keys:
                assert key in item, (
                    f"Attachment {i} missing required key {key!r}; keys present: {list(item.keys())}"
                )
            assert "data" not in item, (
                f"Attachment {i} must NOT contain 'data' key, but got keys: {list(item.keys())}"
            )
    finally:
        _cleanup(tmp.name)


# ---------------------------------------------------------------------------
# Property 9 — Attachment data endpoint round-trip
# Validates: Requirements 9.3
# ---------------------------------------------------------------------------


@given(data=st.binary(min_size=1))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_9_attachment_data_endpoint_round_trip(data):
    """Feature: raw-body-storage, Property 9: Attachment data endpoint round-trip

    For any attachment stored with non-null data, the data endpoint returns
    the exact bytes that were stored.

    **Validates: Requirements 9.3**
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    message_id = str(uuid.uuid4())
    attachment_id = str(uuid.uuid4())
    attachments = [
        {
            "filename": "test.bin",
            "mime_type": "application/octet-stream",
            "size": len(data),
            "data": data,
            "attachment_id": attachment_id,
        }
    ]
    try:
        _seed_message_with_attachments(tmp.name, message_id, attachments)
        client = _make_client(tmp.name)

        resp = client.get(
            f"/api/messages/{message_id}/attachments/{attachment_id}/data"
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}; body: {resp.data!r}"
        )
        assert resp.data == data, (
            f"Response bytes do not match stored bytes. "
            f"Expected {len(data)} bytes, got {len(resp.data)} bytes."
        )
    finally:
        _cleanup(tmp.name)
