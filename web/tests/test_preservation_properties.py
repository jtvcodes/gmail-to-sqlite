"""Preservation property tests for the message detail API.

These tests capture BASELINE behavior that must be preserved after the fix.
They test the API layer (not the JS rendering layer), so they PASS on unfixed code.

The bug is in messageDetail.js (JS rendering), not in the API. These tests verify:
  - Messages with empty to/cc/bcc arrays → API returns empty arrays (no TO/CC/BCC data)
  - From field is returned correctly using sender.name and sender.email
  - Subject, date, labels, body are returned without change

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import json
import sqlite3
import tempfile
import os
import datetime

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from web.server import create_app

# ---------------------------------------------------------------------------
# DB schema (mirrors the real schema)
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE messages (
    message_id    TEXT PRIMARY KEY,
    thread_id     TEXT,
    sender        TEXT,
    recipients    TEXT,
    labels        TEXT,
    subject       TEXT,
    body          TEXT,
    raw           TEXT,
    size          INTEGER,
    timestamp     DATETIME,
    is_read       INTEGER,
    is_outgoing   INTEGER,
    is_deleted    INTEGER,
    last_indexed  DATETIME
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
    attachment_id TEXT,
    content_id    TEXT
)
"""

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=30,
)

safe_text_or_empty = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=0,
    max_size=30,
)

email_strategy = st.builds(
    lambda user, domain: f"{user}@{domain}.com",
    user=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
    domain=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=20,
    ),
)

sender_strategy = st.fixed_dictionaries({
    "name": safe_text,
    "email": email_strategy,
})

label_strategy = safe_text
labels_strategy = st.lists(label_strategy, min_size=0, max_size=5)

timestamp_strategy = st.datetimes(
    min_value=datetime.datetime(2000, 1, 1),
    max_value=datetime.datetime(2030, 12, 31),
).map(lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S"))

subject_strategy = st.one_of(st.none(), safe_text)
body_strategy = st.one_of(st.none(), safe_text)


def message_with_empty_recipients_strategy():
    """Strategy for messages where all recipient arrays are empty.

    These are the messages where isBugCondition does NOT hold for any recipient.
    """
    return st.fixed_dictionaries({
        "sender": sender_strategy,
        "recipients": st.just({"to": [], "cc": [], "bcc": []}),
        "labels": labels_strategy,
        "subject": subject_strategy,
        "body": body_strategy,
        "timestamp": timestamp_strategy,
        "is_read": st.booleans(),
        "is_outgoing": st.booleans(),
    })


# ---------------------------------------------------------------------------
# DB seeding helpers
# ---------------------------------------------------------------------------

def _seed_db_with_message(path: str, msg: dict) -> str:
    """Create the messages table and insert a single message. Returns message_id."""
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
    message_id = "test_msg_1"
    conn.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,?,NULL)",
        (
            message_id,
            "thread1",
            json.dumps(msg["sender"], ensure_ascii=False),
            json.dumps(msg["recipients"], ensure_ascii=False),
            json.dumps(msg["labels"], ensure_ascii=False),
            msg["subject"],
            msg["body"],
            100,
            msg["timestamp"],
            1 if msg["is_read"] else 0,
            1 if msg["is_outgoing"] else 0,
            0,  # is_deleted = False
        ),
    )
    conn.commit()
    conn.close()
    return message_id


def _make_client_with_message(msg: dict):
    """Seed a temp DB with a single message and return a Flask test client."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    message_id = _seed_db_with_message(tmp.name, msg)
    flask_app = create_app(db_path=tmp.name)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    return client, tmp.name, message_id


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Unit tests: Baseline behavior observation (non-property tests)
# These confirm the observed behavior on unfixed code.
# ---------------------------------------------------------------------------


class TestEmptyRecipientsBaselineBehavior:
    """Observe and confirm baseline behavior for messages with empty recipient arrays.

    These tests PASS on unfixed code because the API correctly returns empty arrays.
    The bug is in the JS rendering layer, not the API.
    """

    def test_empty_to_array_returns_empty_list(self):
        """API returns empty list for to when recipients.to is [].

        Validates: Requirement 3.1 (no TO line when no TO recipients)
        """
        msg = {
            "sender": {"name": "Alice", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": ["INBOX"],
            "subject": "Test Subject",
            "body": "Test body",
            "timestamp": "2024-01-10T10:00:00",
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "recipients" in data
            to_list = data["recipients"].get("to", [])
            assert to_list == [], (
                f"Expected empty TO list but got {to_list!r}. "
                "When to=[], the API must return an empty list so no TO line is rendered."
            )
        finally:
            _cleanup(db_path)

    def test_empty_cc_array_returns_empty_list(self):
        """API returns empty list for cc when recipients.cc is [].

        Validates: Requirement 3.2 (no CC line when no CC recipients)
        """
        msg = {
            "sender": {"name": "Alice", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": ["INBOX"],
            "subject": "Test Subject",
            "body": "Test body",
            "timestamp": "2024-01-10T10:00:00",
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            cc_list = data["recipients"].get("cc", [])
            assert cc_list == [], (
                f"Expected empty CC list but got {cc_list!r}. "
                "When cc=[], the API must return an empty list so no CC line is rendered."
            )
        finally:
            _cleanup(db_path)

    def test_empty_bcc_array_returns_empty_list(self):
        """API returns empty list for bcc when recipients.bcc is [].

        Validates: Requirement 3.3 (no BCC line when no BCC recipients)
        """
        msg = {
            "sender": {"name": "Alice", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": ["INBOX"],
            "subject": "Test Subject",
            "body": "Test body",
            "timestamp": "2024-01-10T10:00:00",
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            bcc_list = data["recipients"].get("bcc", [])
            assert bcc_list == [], (
                f"Expected empty BCC list but got {bcc_list!r}. "
                "When bcc=[], the API must return an empty list so no BCC line is rendered."
            )
        finally:
            _cleanup(db_path)

    def test_from_field_returns_sender_name_and_email(self):
        """API returns sender.name and sender.email correctly for the From field.

        Validates: Requirement 3.4 (From field renders correctly)
        """
        msg = {
            "sender": {"name": "Alice Smith", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": ["INBOX"],
            "subject": "Test Subject",
            "body": "Test body",
            "timestamp": "2024-01-10T10:00:00",
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            sender = data.get("sender", {})
            assert sender.get("name") == "Alice Smith", (
                f"Expected sender.name='Alice Smith' but got {sender.get('name')!r}"
            )
            assert sender.get("email") == "alice@example.com", (
                f"Expected sender.email='alice@example.com' but got {sender.get('email')!r}"
            )
        finally:
            _cleanup(db_path)

    def test_subject_returned_unchanged(self):
        """API returns subject exactly as stored.

        Validates: Requirement 3.5 (subject renders without change)
        """
        subject = "My Important Subject"
        msg = {
            "sender": {"name": "Alice", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": ["INBOX"],
            "subject": subject,
            "body": "Test body",
            "timestamp": "2024-01-10T10:00:00",
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get("subject") == subject, (
                f"Expected subject={subject!r} but got {data.get('subject')!r}"
            )
        finally:
            _cleanup(db_path)

    def test_body_returned_unchanged(self):
        """API returns body exactly as stored.

        Validates: Requirement 3.5 (body renders without change)
        """
        body = "This is the message body content."
        msg = {
            "sender": {"name": "Alice", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": ["INBOX"],
            "subject": "Test Subject",
            "body": body,
            "timestamp": "2024-01-10T10:00:00",
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get("body") == body, (
                f"Expected body={body!r} but got {data.get('body')!r}"
            )
        finally:
            _cleanup(db_path)

    def test_labels_returned_unchanged(self):
        """API returns labels list exactly as stored.

        Validates: Requirement 3.5 (labels render without change)
        """
        labels = ["INBOX", "Work", "Important"]
        msg = {
            "sender": {"name": "Alice", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": labels,
            "subject": "Test Subject",
            "body": "Test body",
            "timestamp": "2024-01-10T10:00:00",
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get("labels") == labels, (
                f"Expected labels={labels!r} but got {data.get('labels')!r}"
            )
        finally:
            _cleanup(db_path)

    def test_timestamp_returned_unchanged(self):
        """API returns timestamp exactly as stored.

        Validates: Requirement 3.5 (date renders without change)
        """
        timestamp = "2024-06-15T14:30:00"
        msg = {
            "sender": {"name": "Alice", "email": "alice@example.com"},
            "recipients": {"to": [], "cc": [], "bcc": []},
            "labels": ["INBOX"],
            "subject": "Test Subject",
            "body": "Test body",
            "timestamp": timestamp,
            "is_read": False,
            "is_outgoing": False,
        }
        client, db_path, message_id = _make_client_with_message(msg)
        try:
            resp = client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get("timestamp") == timestamp, (
                f"Expected timestamp={timestamp!r} but got {data.get('timestamp')!r}"
            )
        finally:
            _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property-based tests: Preservation properties
# These PASS on unfixed code — they verify API behavior, not JS rendering.
# ---------------------------------------------------------------------------


@given(msg=message_with_empty_recipients_strategy())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_3_1_empty_to_array_never_produces_to_data(msg):
    """Property 3.1: For all messages with empty to array, API returns empty to list.

    When recipients.to is [], the API must return an empty list for to.
    The JS rendering layer checks `recipients.to.length > 0` before rendering the TO line,
    so an empty array means no TO line is rendered. This behavior must be preserved.

    **Validates: Requirements 3.1**
    """
    assert msg["recipients"]["to"] == [], "Strategy should produce empty to array"

    client, db_path, message_id = _make_client_with_message(msg)
    try:
        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "recipients" in data, "API response must include 'recipients' field"
        to_list = data["recipients"].get("to", [])
        assert to_list == [], (
            f"Expected empty TO list for message with no TO recipients, "
            f"but got {to_list!r}. "
            "An empty to array must be preserved so no TO line is rendered."
        )
    finally:
        _cleanup(db_path)


@given(msg=message_with_empty_recipients_strategy())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_3_2_empty_cc_array_never_produces_cc_data(msg):
    """Property 3.2: For all messages with empty cc array, API returns empty cc list.

    When recipients.cc is [], the API must return an empty list for cc.
    The JS rendering layer checks `recipients.cc.length > 0` before rendering the CC line,
    so an empty array means no CC line is rendered. This behavior must be preserved.

    **Validates: Requirements 3.2**
    """
    assert msg["recipients"]["cc"] == [], "Strategy should produce empty cc array"

    client, db_path, message_id = _make_client_with_message(msg)
    try:
        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "recipients" in data, "API response must include 'recipients' field"
        cc_list = data["recipients"].get("cc", [])
        assert cc_list == [], (
            f"Expected empty CC list for message with no CC recipients, "
            f"but got {cc_list!r}. "
            "An empty cc array must be preserved so no CC line is rendered."
        )
    finally:
        _cleanup(db_path)


@given(msg=message_with_empty_recipients_strategy())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_3_3_empty_bcc_array_never_produces_bcc_data(msg):
    """Property 3.3: For all messages with empty bcc array, API returns empty bcc list.

    When recipients.bcc is [], the API must return an empty list for bcc.
    The JS rendering layer checks `recipients.bcc.length > 0` before rendering the BCC line,
    so an empty array means no BCC line is rendered. This behavior must be preserved.

    **Validates: Requirements 3.3**
    """
    assert msg["recipients"]["bcc"] == [], "Strategy should produce empty bcc array"

    client, db_path, message_id = _make_client_with_message(msg)
    try:
        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "recipients" in data, "API response must include 'recipients' field"
        bcc_list = data["recipients"].get("bcc", [])
        assert bcc_list == [], (
            f"Expected empty BCC list for message with no BCC recipients, "
            f"but got {bcc_list!r}. "
            "An empty bcc array must be preserved so no BCC line is rendered."
        )
    finally:
        _cleanup(db_path)


@given(msg=message_with_empty_recipients_strategy())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_3_4_from_field_uses_sender_name_and_email(msg):
    """Property 3.4: For all messages, the From field uses sender.name and sender.email.

    The API must return sender as a {name, email} dict. The JS rendering uses:
      "From: " + (sender.name || "") + " <" + (sender.email || "") + ">"
    This inline template is NOT affected by the fix. The API must continue to return
    sender.name and sender.email exactly as stored.

    **Validates: Requirements 3.4**
    """
    expected_name = msg["sender"]["name"]
    expected_email = msg["sender"]["email"]

    client, db_path, message_id = _make_client_with_message(msg)
    try:
        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "sender" in data, "API response must include 'sender' field"
        sender = data["sender"]
        assert isinstance(sender, dict), (
            f"Expected sender to be a dict but got {type(sender)}"
        )
        assert sender.get("name") == expected_name, (
            f"Expected sender.name={expected_name!r} but got {sender.get('name')!r}. "
            "The From field must use sender.name exactly as stored."
        )
        assert sender.get("email") == expected_email, (
            f"Expected sender.email={expected_email!r} but got {sender.get('email')!r}. "
            "The From field must use sender.email exactly as stored."
        )
    finally:
        _cleanup(db_path)


@given(msg=message_with_empty_recipients_strategy())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_3_5_subject_date_labels_body_unaffected(msg):
    """Property 3.5: For all messages, subject, date, labels, and body are unaffected.

    The API must return subject, timestamp, labels, and body exactly as stored.
    These fields are not related to recipient rendering and must not be changed by the fix.

    **Validates: Requirements 3.5**
    """
    client, db_path, message_id = _make_client_with_message(msg)
    try:
        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200
        data = resp.get_json()

        # Subject: returned as stored (None becomes null in JSON → None in Python)
        assert data.get("subject") == msg["subject"], (
            f"Expected subject={msg['subject']!r} but got {data.get('subject')!r}. "
            "Subject must be returned unchanged."
        )

        # Timestamp: returned as stored
        assert data.get("timestamp") == msg["timestamp"], (
            f"Expected timestamp={msg['timestamp']!r} but got {data.get('timestamp')!r}. "
            "Timestamp must be returned unchanged."
        )

        # Labels: returned as stored list
        assert data.get("labels") == msg["labels"], (
            f"Expected labels={msg['labels']!r} but got {data.get('labels')!r}. "
            "Labels must be returned unchanged."
        )

        # Body: returned as stored (None becomes null in JSON → None in Python)
        assert data.get("body") == msg["body"], (
            f"Expected body={msg['body']!r} but got {data.get('body')!r}. "
            "Body must be returned unchanged."
        )
    finally:
        _cleanup(db_path)


# ===========================================================================
# Missing-DB-UX Bugfix: Preservation Property Tests
#
# These tests capture BASELINE behavior that the fix must NOT break.
# They PASS on unfixed code — they verify existing API behavior against a
# populated database (or a non-table-missing error), not the bug condition.
#
# Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
# ===========================================================================

import unittest.mock as mock

# ---------------------------------------------------------------------------
# Shared DB helpers (reuse CREATE_TABLE_SQL and SEED_ROWS from test_web_messages)
# ---------------------------------------------------------------------------

PRESERVATION_SEED_ROWS = [
    (
        "pmsg1", "thread1",
        '{"name": "Alice", "email": "alice@example.com"}',
        '{"to": ["bob@example.com"], "cc": [], "bcc": []}',
        '["INBOX", "Work"]',
        "Hello Bob", "Hi there, how are you?", 100,
        "2024-01-10T10:00:00", 0, 0, 0,
    ),
    (
        "pmsg2", "thread2",
        '{"name": "Bob", "email": "bob@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["INBOX"]',
        "Re: Hello Bob", "I am fine, thanks!", 80,
        "2024-01-09T09:00:00", 1, 0, 0,
    ),
    (
        "pmsg3", "thread3",
        '{"name": "Charlie", "email": "charlie@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["SENT"]',
        "Meeting tomorrow", "Let us meet at 10am.", 120,
        "2024-01-08T08:00:00", 1, 1, 0,
    ),
]


def _seed_preservation_db(path: str) -> None:
    """Create and seed the messages table for preservation tests."""
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,?,NULL)",
        PRESERVATION_SEED_ROWS,
    )
    conn.commit()
    conn.close()


def _make_populated_client():
    """Return a Flask test client backed by a seeded (populated) DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _seed_preservation_db(tmp.name)
    flask_app = create_app(db_path=tmp.name)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    return client, tmp.name


# ---------------------------------------------------------------------------
# Hypothesis strategies for preservation tests
# ---------------------------------------------------------------------------

# Valid page values: 1..100
valid_page_st = st.integers(min_value=1, max_value=100)

# Valid page_size values: 1..200
valid_page_size_st = st.integers(min_value=1, max_value=200)

# Optional filter params (None means omit from query string)
optional_q_st = st.one_of(st.none(), st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1, max_size=20,
))
optional_label_st = st.one_of(st.none(), st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1, max_size=20,
))
optional_bool_st = st.one_of(st.none(), st.sampled_from(["true", "false"]))

# Unknown message_id: a UUID-like string guaranteed not to be in the seeded DB
unknown_message_id_st = st.uuids().map(str)


def _int_accepts(s: str) -> bool:
    """Return True if Python's int() would successfully parse s."""
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


# Invalid page values: zero, negative, or non-numeric
# Note: filter out strings that int() would accept (int() strips whitespace)
invalid_page_st = st.one_of(
    st.integers(max_value=0),
    st.text(min_size=1, max_size=10).filter(
        lambda s: not s.lstrip("-").isdigit() and not _int_accepts(s)
    ),
)

# Invalid page_size values: zero, negative, above 200, or non-numeric
invalid_page_size_st = st.one_of(
    st.integers(max_value=0),
    st.integers(min_value=201),
    st.text(min_size=1, max_size=10).filter(
        lambda s: not s.lstrip("-").isdigit() and not _int_accepts(s)
    ),
)


# ---------------------------------------------------------------------------
# Requirement 3.1: GET /api/messages with populated table → HTTP 200 + envelope
# ---------------------------------------------------------------------------

@given(
    page=valid_page_st,
    page_size=valid_page_size_st,
    q=optional_q_st,
    label=optional_label_st,
    is_read=optional_bool_st,
    is_outgoing=optional_bool_st,
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much], deadline=None)
def test_preservation_3_1_list_messages_populated_db_returns_200_with_envelope(
    page, page_size, q, label, is_read, is_outgoing
):
    """Preservation 3.1: GET /api/messages with populated table → HTTP 200 with envelope.

    For all valid query-parameter combinations against a populated DB, the
    endpoint must return HTTP 200 with the correct envelope structure:
    {messages, total, page, page_size}.

    This behavior must be preserved after the fix.

    **Validates: Requirements 3.1**
    """
    client, db_path = _make_populated_client()
    try:
        params = [f"page={page}", f"page_size={page_size}"]
        if q is not None:
            params.append(f"q={q}")
        if label is not None:
            params.append(f"label={label}")
        if is_read is not None:
            params.append(f"is_read={is_read}")
        if is_outgoing is not None:
            params.append(f"is_outgoing={is_outgoing}")
        url = "/api/messages?" + "&".join(params)

        resp = client.get(url)
        assert resp.status_code == 200, (
            f"Expected HTTP 200 for {url!r} against populated DB, "
            f"got {resp.status_code} (body: {resp.get_data(as_text=True)!r})"
        )
        data = resp.get_json()
        assert data is not None, "Response body must be valid JSON"
        for field in ("messages", "total", "page", "page_size"):
            assert field in data, (
                f"Envelope field {field!r} missing from response to {url!r}. "
                f"Got: {list(data.keys())}"
            )
        assert isinstance(data["messages"], list), (
            f"'messages' must be a list, got {type(data['messages'])}"
        )
        assert isinstance(data["total"], int), (
            f"'total' must be an int, got {type(data['total'])}"
        )
        assert data["page"] == page, (
            f"'page' in response ({data['page']}) must equal requested page ({page})"
        )
        assert data["page_size"] == page_size, (
            f"'page_size' in response ({data['page_size']}) must equal requested page_size ({page_size})"
        )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Requirement 3.2: GET /api/messages/<valid_id> → HTTP 200 with message detail
# ---------------------------------------------------------------------------

@given(
    message_index=st.integers(min_value=0, max_value=len(PRESERVATION_SEED_ROWS) - 1),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_preservation_3_2_get_message_valid_id_returns_200_with_detail(message_index):
    """Preservation 3.2: GET /api/messages/<valid_id> → HTTP 200 with message detail.

    For all valid message_ids present in the DB, the endpoint must return
    HTTP 200 with the full message detail object including all required fields.

    This behavior must be preserved after the fix.

    **Validates: Requirements 3.2**
    """
    client, db_path = _make_populated_client()
    try:
        message_id = PRESERVATION_SEED_ROWS[message_index][0]
        resp = client.get(f"/api/messages/{message_id}")
        assert resp.status_code == 200, (
            f"Expected HTTP 200 for GET /api/messages/{message_id}, "
            f"got {resp.status_code} (body: {resp.get_data(as_text=True)!r})"
        )
        data = resp.get_json()
        assert data is not None, "Response body must be valid JSON"
        for field in ("message_id", "thread_id", "sender", "labels", "subject",
                      "timestamp", "is_read", "is_outgoing", "is_deleted",
                      "recipients", "body"):
            assert field in data, (
                f"Detail field {field!r} missing from GET /api/messages/{message_id}. "
                f"Got: {list(data.keys())}"
            )
        assert data["message_id"] == message_id, (
            f"Returned message_id {data['message_id']!r} != requested {message_id!r}"
        )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Requirement 3.3: GET /api/messages/<unknown_id> → HTTP 404 with error body
# ---------------------------------------------------------------------------

@given(unknown_id=unknown_message_id_st)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_preservation_3_3_get_message_unknown_id_returns_404(unknown_id):
    """Preservation 3.3: GET /api/messages/<unknown_id> → HTTP 404 with error body.

    For all message_id values not present in the DB, the endpoint must return
    HTTP 404 with exactly {"error": "Message not found"}.

    This behavior must be preserved after the fix.

    **Validates: Requirements 3.3**
    """
    client, db_path = _make_populated_client()
    try:
        # UUIDs are guaranteed not to match the seeded pmsg1/pmsg2/pmsg3 IDs
        resp = client.get(f"/api/messages/{unknown_id}")
        assert resp.status_code == 404, (
            f"Expected HTTP 404 for unknown message_id {unknown_id!r}, "
            f"got {resp.status_code} (body: {resp.get_data(as_text=True)!r})"
        )
        data = resp.get_json()
        assert data == {"error": "Message not found"}, (
            f"Expected body {{'error': 'Message not found'}} for unknown id, "
            f"got {data!r}"
        )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Requirement 3.4: Invalid page/page_size → HTTP 400 with "error" field
# ---------------------------------------------------------------------------

@given(
    invalid_param=st.one_of(
        st.tuples(st.just("page"), invalid_page_st),
        st.tuples(st.just("page_size"), invalid_page_size_st),
    )
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=None,
)
def test_preservation_3_4_invalid_pagination_returns_400_with_error(invalid_param):
    """Preservation 3.4: Invalid page/page_size → HTTP 400 with "error" field.

    For all invalid page or page_size values, the endpoint must return HTTP 400
    with a JSON body containing an "error" field.

    This behavior must be preserved after the fix.

    **Validates: Requirements 3.4**
    """
    client, db_path = _make_populated_client()
    try:
        param_name, param_value = invalid_param
        resp = client.get(f"/api/messages?{param_name}={param_value}")
        assert resp.status_code == 400, (
            f"Expected HTTP 400 for {param_name}={param_value!r}, "
            f"got {resp.status_code} (body: {resp.get_data(as_text=True)!r})"
        )
        data = resp.get_json()
        assert data is not None, "Response body must be valid JSON"
        assert "error" in data, (
            f"Expected 'error' field in 400 response for {param_name}={param_value!r}, "
            f"got {data!r}"
        )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Requirement 3.5: Non-table-missing OperationalError → HTTP 500 with original error
# ---------------------------------------------------------------------------

def test_preservation_3_5_non_table_missing_error_returns_500():
    """Preservation 3.5: Non-table-missing OperationalError → HTTP 500 with original error.

    When a SQLite OperationalError that is NOT "no such table: messages" is
    raised, the endpoint must return HTTP 500 with the original error string
    in the "error" field — NOT HTTP 503.

    This behavior must be preserved after the fix.

    **Validates: Requirements 3.5**
    """
    import sqlite3 as _sqlite3
    from unittest.mock import patch, MagicMock

    # Use a real populated DB so the app starts up fine
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _seed_preservation_db(tmp.name)
    flask_app = create_app(db_path=tmp.name)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()

    # Simulate a non-table-missing OperationalError (e.g. disk I/O error)
    non_table_error = _sqlite3.OperationalError("disk I/O error")

    try:
        with flask_app.app_context():
            with patch("web.api.messages.get_db") as mock_get_db:
                mock_conn = MagicMock()
                mock_conn.execute.side_effect = non_table_error
                mock_get_db.return_value = mock_conn

                resp = client.get("/api/messages")
                assert resp.status_code == 500, (
                    f"Expected HTTP 500 for non-table-missing OperationalError, "
                    f"got {resp.status_code} (body: {resp.get_data(as_text=True)!r})"
                )
                data = resp.get_json()
                assert data is not None, "Response body must be valid JSON"
                assert "error" in data, (
                    f"Expected 'error' field in 500 response, got {data!r}"
                )
                assert "disk I/O error" in data["error"], (
                    f"Expected original error string 'disk I/O error' in response, "
                    f"got {data['error']!r}"
                )
    finally:
        _cleanup(tmp.name)


def test_preservation_3_5_non_table_missing_error_get_message_returns_500():
    """Preservation 3.5 (get_message): Non-table-missing OperationalError → HTTP 500.

    Same as above but for GET /api/messages/<id>.

    **Validates: Requirements 3.5**
    """
    import sqlite3 as _sqlite3
    from unittest.mock import patch, MagicMock

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _seed_preservation_db(tmp.name)
    flask_app = create_app(db_path=tmp.name)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()

    non_table_error = _sqlite3.OperationalError("disk I/O error")

    try:
        with flask_app.app_context():
            with patch("web.api.messages.get_db") as mock_get_db:
                mock_conn = MagicMock()
                mock_conn.execute.side_effect = non_table_error
                mock_get_db.return_value = mock_conn

                resp = client.get("/api/messages/pmsg1")
                assert resp.status_code == 500, (
                    f"Expected HTTP 500 for non-table-missing OperationalError in get_message, "
                    f"got {resp.status_code} (body: {resp.get_data(as_text=True)!r})"
                )
                data = resp.get_json()
                assert data is not None, "Response body must be valid JSON"
                assert "error" in data, (
                    f"Expected 'error' field in 500 response, got {data!r}"
                )
                assert "disk I/O error" in data["error"], (
                    f"Expected original error string 'disk I/O error' in response, "
                    f"got {data['error']!r}"
                )
    finally:
        _cleanup(tmp.name)
