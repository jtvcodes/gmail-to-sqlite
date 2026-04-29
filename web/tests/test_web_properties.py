"""Property-based tests for the Gmail Web Viewer API.

All tests use an in-memory SQLite database seeded by Hypothesis strategies.
The real data/messages.db is never touched.
"""

import json
import sqlite3
import tempfile
import os
import uuid

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from web.server import create_app

# ---------------------------------------------------------------------------
# DB schema
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

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Safe alphanumeric text for labels and search terms
safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=20,
)

label_strategy = safe_text
search_term_strategy = safe_text

page_size_strategy = st.integers(min_value=1, max_value=200)
page_strategy = st.integers(min_value=1, max_value=10)


def message_strategy(labels_pool=None):
    """Strategy that generates a single message record dict."""
    # Use safe_text for email to avoid special chars that could confuse LIKE queries
    email_st = st.builds(
        lambda user, domain: f"{user}@{domain}.com",
        user=safe_text,
        domain=safe_text,
    )
    sender_st = st.fixed_dictionaries({
        "name": safe_text,
        "email": email_st,
    })
    recipients_st = st.just({"to": [], "cc": [], "bcc": []})
    labels_st = (
        st.lists(st.sampled_from(labels_pool), min_size=0, max_size=3)
        if labels_pool
        else st.lists(safe_text, min_size=0, max_size=3)
    )
    return st.fixed_dictionaries({
        "thread_id": safe_text,
        "sender": sender_st,
        "recipients": recipients_st,
        "labels": labels_st,
        "subject": st.one_of(st.none(), safe_text),
        "body": st.one_of(st.none(), safe_text),
        "size": st.integers(min_value=1, max_value=10000),
        "timestamp": st.datetimes(
            min_value=__import__("datetime").datetime(2000, 1, 1),
            max_value=__import__("datetime").datetime(2030, 12, 31),
        ).map(lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S")),
        "is_read": st.booleans(),
        "is_outgoing": st.booleans(),
        "is_deleted": st.booleans(),
    })


messages_list_strategy = st.lists(message_strategy(), min_size=0, max_size=20)


# ---------------------------------------------------------------------------
# DB seeding helpers
# ---------------------------------------------------------------------------

def _seed_db(path: str, messages: list) -> None:
    """Create the messages table and insert the given records."""
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    for i, msg in enumerate(messages):
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,NULL,?,?,?,?,?,NULL)",
            (
                str(i),  # unique message_id by index
                msg["thread_id"],
                # Use ensure_ascii=False so stored text matches deserialized values
                # (avoids unicode escapes like \u00b5 that could cause false LIKE matches)
                json.dumps(msg["sender"], ensure_ascii=False),
                json.dumps(msg["recipients"], ensure_ascii=False),
                json.dumps(msg["labels"], ensure_ascii=False),
                msg["subject"],
                msg["body"],
                msg["size"],
                msg["timestamp"],
                1 if msg["is_read"] else 0,
                1 if msg["is_outgoing"] else 0,
                1 if msg["is_deleted"] else 0,
            ),
        )
    conn.commit()
    conn.close()


def _make_client(messages: list):
    """Seed a temp DB with *messages* and return a Flask test client."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _seed_db(tmp.name, messages)
    flask_app = create_app(db_path=tmp.name)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    return client, tmp.name


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Property 1: Pagination total consistency
# Validates: Requirements 2.5
# ---------------------------------------------------------------------------

@given(
    messages=messages_list_strategy,
    page=page_strategy,
    page_size=page_size_strategy,
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_1_pagination_total_consistency(messages, page, page_size):
    # Feature: gmail-web-viewer, Property 1: Pagination total consistency
    client, db_path = _make_client(messages)
    try:
        resp = client.get(f"/api/messages?page={page}&page_size={page_size}")
        assert resp.status_code == 200
        data = resp.get_json()

        # Verify total matches a direct COUNT of non-deleted messages
        conn = sqlite3.connect(db_path)
        direct_count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE is_deleted = 0"
        ).fetchone()[0]
        conn.close()

        assert data["total"] == direct_count
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property 2: Page size bounds
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------

@given(
    messages=messages_list_strategy,
    page=page_strategy,
    page_size=page_size_strategy,
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_2_page_size_bounds(messages, page, page_size):
    # Feature: gmail-web-viewer, Property 2: Page size bounds
    client, db_path = _make_client(messages)
    try:
        resp = client.get(f"/api/messages?page={page}&page_size={page_size}")
        assert resp.status_code == 200
        data = resp.get_json()

        returned = data["messages"]
        total = data["total"]

        assert len(returned) <= page_size
        assert len(returned) <= total
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property 3: Search filter soundness
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------

@given(
    messages=messages_list_strategy,
    query=search_term_strategy,
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_3_search_filter_soundness(messages, query):
    # Feature: gmail-web-viewer, Property 3: Search filter soundness
    client, db_path = _make_client(messages)
    try:
        resp = client.get(f"/api/messages?q={query}&page_size=200")
        assert resp.status_code == 200
        data = resp.get_json()

        q_lower = query.lower()
        for msg in data["messages"]:
            subject = (msg.get("subject") or "").lower()
            sender = msg.get("sender") or {}
            sender_name = (sender.get("name") or "").lower()
            sender_email = (sender.get("email") or "").lower()
            body = (msg.get("body") or "").lower()

            matches = (
                q_lower in subject
                or q_lower in sender_name
                or q_lower in sender_email
                or q_lower in body
            )
            assert matches, (
                f"Message {msg['message_id']} does not contain query {query!r}. "
                f"subject={msg.get('subject')!r}, sender={msg.get('sender')!r}, body={msg.get('body')!r}"
            )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property 4: Label filter soundness
# Validates: Requirements 3.2
# ---------------------------------------------------------------------------

@given(
    messages=messages_list_strategy,
    label=label_strategy,
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_4_label_filter_soundness(messages, label):
    # Feature: gmail-web-viewer, Property 4: Label filter soundness
    client, db_path = _make_client(messages)
    try:
        resp = client.get(f"/api/messages?label={label}&page_size=200")
        assert resp.status_code == 200
        data = resp.get_json()

        for msg in data["messages"]:
            msg_labels = msg.get("labels") or []
            assert label in msg_labels, (
                f"Message {msg['message_id']} labels {msg_labels!r} "
                f"do not contain label {label!r}"
            )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property 5: Boolean filter soundness
# Validates: Requirements 3.3, 3.4
# ---------------------------------------------------------------------------

@given(
    messages=messages_list_strategy,
    is_read=st.booleans(),
    is_outgoing=st.booleans(),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_5_boolean_filter_soundness(messages, is_read, is_outgoing):
    # Feature: gmail-web-viewer, Property 5: Boolean filter soundness
    client, db_path = _make_client(messages)
    try:
        is_read_str = "true" if is_read else "false"
        is_outgoing_str = "true" if is_outgoing else "false"
        resp = client.get(
            f"/api/messages?is_read={is_read_str}&is_outgoing={is_outgoing_str}&page_size=200"
        )
        assert resp.status_code == 200
        data = resp.get_json()

        for msg in data["messages"]:
            assert msg["is_read"] == is_read, (
                f"Message {msg['message_id']} is_read={msg['is_read']!r} "
                f"but filter requested is_read={is_read!r}"
            )
            assert msg["is_outgoing"] == is_outgoing, (
                f"Message {msg['message_id']} is_outgoing={msg['is_outgoing']!r} "
                f"but filter requested is_outgoing={is_outgoing!r}"
            )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property 6: Deleted messages excluded by default
# Validates: Requirements 6.1
# ---------------------------------------------------------------------------

@given(messages=messages_list_strategy)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_6_deleted_messages_excluded_by_default(messages):
    # Feature: gmail-web-viewer, Property 6: Deleted messages excluded by default
    client, db_path = _make_client(messages)
    try:
        resp = client.get("/api/messages?page_size=200")
        assert resp.status_code == 200
        data = resp.get_json()

        for msg in data["messages"]:
            assert msg["is_deleted"] is False, (
                f"Message {msg['message_id']} has is_deleted=True "
                "but include_deleted was not set"
            )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property 7: Labels endpoint completeness
# Validates: Requirements 5.1
# ---------------------------------------------------------------------------

@given(messages=messages_list_strategy)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_property_7_labels_endpoint_completeness(messages):
    # Feature: gmail-web-viewer, Property 7: Labels endpoint completeness
    client, db_path = _make_client(messages)
    try:
        resp = client.get("/api/labels")
        assert resp.status_code == 200
        returned_labels = resp.get_json()
        assert isinstance(returned_labels, list)

        # Collect all labels from non-deleted messages
        expected_labels = set()
        for msg in messages:
            if not msg["is_deleted"]:
                for lbl in msg.get("labels") or []:
                    if isinstance(lbl, str):
                        expected_labels.add(lbl)

        # Every expected label must appear in the response
        for lbl in expected_labels:
            assert lbl in returned_labels, (
                f"Label {lbl!r} from a non-deleted message is missing from /api/labels"
            )

        # Response must be sorted alphabetically
        assert returned_labels == sorted(returned_labels), (
            f"Labels are not sorted alphabetically: {returned_labels!r}"
        )
    finally:
        _cleanup(db_path)


# ---------------------------------------------------------------------------
# Property 8: Invalid pagination parameters rejected
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

invalid_page_strategy = st.one_of(
    st.integers(max_value=0),                          # zero or negative
    st.text(min_size=1, max_size=10).filter(           # non-numeric strings
        lambda s: not s.lstrip("-").isdigit()
    ),
)

invalid_page_size_strategy = st.one_of(
    st.integers(max_value=0),                          # zero or negative
    st.integers(min_value=201),                        # above max
    st.text(min_size=1, max_size=10).filter(           # non-numeric strings
        lambda s: not s.lstrip("-").isdigit()
    ),
)


@given(
    messages=st.lists(message_strategy(), min_size=0, max_size=5),
    invalid_param=st.one_of(
        st.tuples(st.just("page"), invalid_page_strategy),
        st.tuples(st.just("page_size"), invalid_page_size_strategy),
    ),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much], deadline=None)
def test_property_8_invalid_pagination_rejected(messages, invalid_param):
    # Feature: gmail-web-viewer, Property 8: Invalid pagination parameters rejected
    client, db_path = _make_client(messages)
    try:
        param_name, param_value = invalid_param
        resp = client.get(f"/api/messages?{param_name}={param_value}")
        assert resp.status_code == 400, (
            f"Expected HTTP 400 for {param_name}={param_value!r}, "
            f"got {resp.status_code}"
        )
        body = resp.get_json()
        assert "error" in body
    finally:
        _cleanup(db_path)
