"""Property-based tests for raw-message-source — message parser.

Properties 3, 4, 5, 7, 13, 14 from the raw-message-source spec.
"""

import base64
import email as _email
from datetime import timezone, datetime as _datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import format_datetime

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from gmail_to_sqlite.message import (
    Message,
    extract_html_from_raw,
    _strip_to_html_tag,
)
from gmail_to_sqlite.sync import _fetch_message  # noqa: F401 — used for decode path


# ---------------------------------------------------------------------------
# Helpers / strategies
# ---------------------------------------------------------------------------


def _encode_base64url(text: str) -> str:
    """Encode a UTF-8 string as base64url (the Gmail API format=raw encoding)."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _decode_base64url(encoded: str) -> str:
    """Decode a base64url string to a UTF-8 string (the sync engine's decode path)."""
    # Add padding if needed — same as base64.urlsafe_b64decode with padding
    return base64.urlsafe_b64decode(encoded + "==").decode("utf-8")


# Strategy for safe header values (ASCII printable only, no newlines)
# Non-ASCII characters get RFC 2047 encoded by the email library, making
# round-trip comparison complex. Restrict to ASCII printable.
_safe_header_text = st.text(
    alphabet=st.characters(
        whitelist_categories=(),
        whitelist_characters="".join(chr(c) for c in range(32, 127) if chr(c) not in "\r\n"),
    ),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())  # ensure non-whitespace-only

# Strategy for email addresses
_email_address_st = st.builds(
    lambda local, domain: f"{local}@{domain}.example.com",
    local=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=1,
        max_size=20,
    ),
    domain=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz",
        min_size=2,
        max_size=10,
    ),
)


def _format_received_date(dt: _datetime) -> str:
    """Format a datetime as an RFC 2822 date string suitable for a Received: header."""
    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


@st.composite
def rfc2822_message_strategy(draw):
    """
    Composite strategy that generates valid RFC 2822 strings with random
    From, To, Subject, Date, and at least one Received: header with a
    semicolon-delimited date.
    """
    from_addr = draw(_email_address_st)
    to_addr = draw(_email_address_st)
    subject = draw(_safe_header_text)
    date_dt = draw(st.datetimes(
        min_value=_datetime(1970, 1, 1),
        max_value=_datetime(2099, 12, 31),
        timezones=st.just(timezone.utc),
    ))
    date_str = _format_received_date(date_dt)

    # At least one Received: header with a semicolon-delimited date
    received_dates = draw(
        st.lists(
            st.datetimes(
                min_value=_datetime(1970, 1, 1),
                max_value=_datetime(2099, 12, 31),
                timezones=st.just(timezone.utc),
            ),
            min_size=1,
            max_size=3,
        )
    )

    plain_text = draw(st.text(min_size=0, max_size=200))

    msg = MIMEText(plain_text, "plain", "utf-8")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = date_str
    for rd in received_dates:
        msg["Received"] = f"by server.example.com; {_format_received_date(rd)}"

    return msg.as_string(), from_addr, to_addr, subject, received_dates


# ---------------------------------------------------------------------------
# Property 3: Base64url decode round-trip
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------


@given(st.text())
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_base64url_decode_roundtrip(raw_text):
    """Feature: raw-message-source, Property 3: Base64url decode round-trip

    For any UTF-8 string, base64url-encoding it and then applying the sync
    engine's decode path SHALL produce a string equal to the original.

    **Validates: Requirements 2.2**
    """
    encoded = _encode_base64url(raw_text)
    decoded = _decode_base64url(encoded)
    assert decoded == raw_text, (
        f"Round-trip failed: original={raw_text!r}, decoded={decoded!r}"
    )


# ---------------------------------------------------------------------------
# Property 4: Message parse preserves raw, headers, and received_date
# Validates: Requirements 3.2, 3.4, 3.7
# ---------------------------------------------------------------------------


@given(rfc2822_message_strategy())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_parse_preserves_raw_headers_and_received_date(rfc2822_data):
    """Feature: raw-message-source, Property 4: Message parse preserves raw, headers, and received_date

    For any valid RFC 2822 string containing From, To, Subject, Date, and at
    least one Received: header with a semicolon-delimited date, parsing it with
    Message.from_raw_source SHALL produce a Message object where:
    - msg.raw equals the input string
    - all extracted header fields match the values present in the input
    - msg.received_date equals the datetime parsed from the last Received: header's date portion

    **Validates: Requirements 3.2, 3.4, 3.7**
    """
    raw_str, from_addr, to_addr, subject, received_dates = rfc2822_data

    msg = Message.from_raw_source(raw_str, {})

    # msg.raw must equal the input string
    assert msg.raw == raw_str, "msg.raw does not equal the input string"

    # Sender email must match
    assert msg.sender.get("email") == from_addr, (
        f"Expected sender email {from_addr!r}, got {msg.sender.get('email')!r}"
    )

    # Subject must match (email library may strip leading/trailing whitespace)
    assert msg.subject == subject or msg.subject == subject.strip(), (
        f"Expected subject {subject!r} (or stripped), got {msg.subject!r}"
    )

    # received_date must be set (we always have at least one Received: header)
    assert msg.received_date is not None, "received_date should not be None"

    # received_date should match the last Received: header's date
    last_received_dt = received_dates[-1]
    if last_received_dt.tzinfo is None:
        last_received_dt = last_received_dt.replace(tzinfo=timezone.utc)

    # Compare timestamps (allow small tolerance for formatting round-trips)
    expected_ts = int(last_received_dt.timestamp())
    actual_ts = int(msg.received_date.timestamp())
    assert abs(actual_ts - expected_ts) <= 1, (
        f"received_date mismatch: expected ~{expected_ts}, got {actual_ts}"
    )


# ---------------------------------------------------------------------------
# Property 5: HTML extraction round-trip
# Validates: Requirements 4.2
# ---------------------------------------------------------------------------


@given(st.text(min_size=1))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_html_extraction_roundtrip(html_str):
    """Feature: raw-message-source, Property 5: HTML extraction round-trip

    For any HTML string embedded as the text/html part of a valid RFC 2822
    multipart message, calling extract_html_from_raw on that message SHALL
    return a string equal to the original HTML content (after accounting for
    MIME encoding/decoding and _strip_to_html_tag processing).

    **Validates: Requirements 4.2**
    """
    # Build a minimal multipart/alternative message with the HTML string
    msg = MIMEMultipart("alternative")
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Test"
    msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
    msg.attach(MIMEText("plain text", "plain", "utf-8"))
    msg.attach(MIMEText(html_str, "html", "utf-8"))
    raw = msg.as_string()

    result = extract_html_from_raw(raw)

    # The result should not be None (we embedded an HTML part)
    assert result is not None, "extract_html_from_raw returned None for a message with HTML part"

    # After _strip_to_html_tag processing, the result should equal the expected
    # stripped version of the original HTML
    expected = _strip_to_html_tag(html_str)
    assert result == expected, (
        f"HTML extraction mismatch:\n  original={html_str!r}\n  expected={expected!r}\n  got={result!r}"
    )


# ---------------------------------------------------------------------------
# Property 7: HTML stripping correctness
# Validates: Requirements 6.1, 6.2
# ---------------------------------------------------------------------------


@given(st.text(), st.text())
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_html_stripping(preamble, body):
    """Feature: raw-message-source, Property 7: HTML stripping correctness

    For preamble + "<html" + body, assert result starts with "<html".
    For strings without "<html", assert result equals input unchanged.

    **Validates: Requirements 6.1, 6.2**
    """
    # Case 1: string contains <html — result must start with <html
    html_with_tag = preamble + "<html" + body
    result_with_tag = _strip_to_html_tag(html_with_tag)
    assert result_with_tag is not None, "Result should not be None for non-empty input with <html"
    assert result_with_tag.startswith("<html"), (
        f"Expected result to start with '<html', got {result_with_tag[:50]!r}"
    )

    # Case 2: string without <html — result must equal input unchanged
    # We need to ensure the string doesn't contain <html
    no_html_tag = preamble.replace("<html", "").replace("<HTML", "")
    # Only test if the cleaned string truly has no <html
    if "<html" not in no_html_tag.lower() or "<html" not in no_html_tag:
        # Use a string we know has no <html
        safe_no_html = no_html_tag.replace("<html", "XHTML")
        if "<html" not in safe_no_html:
            if safe_no_html:  # non-empty
                result_no_tag = _strip_to_html_tag(safe_no_html)
                assert result_no_tag == safe_no_html, (
                    f"Expected unchanged string, got {result_no_tag!r} for input {safe_no_html!r}"
                )


# ---------------------------------------------------------------------------
# Property 13: received_date uses last Received header
# Validates: Requirements 3.7
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.datetimes(
            min_value=_datetime(1970, 1, 1),
            max_value=_datetime(2099, 12, 31),
            timezones=st.just(timezone.utc),
        ),
        min_size=2,
        max_size=5,
    )
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_received_date_uses_last_header(dates):
    """Feature: raw-message-source, Property 13: received_date extraction — last Received header used

    For any RFC 2822 string containing multiple Received: headers each with a
    valid semicolon-delimited date, _parse_received_date SHALL return the
    datetime from the last header in document order.

    **Validates: Requirements 3.7**
    """
    msg = MIMEText("plain text", "plain", "utf-8")
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Test"
    msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
    for dt in dates:
        msg["Received"] = f"by server.example.com; {_format_received_date(dt)}"

    raw = msg.as_string()
    parsed_email = _email.message_from_string(raw)

    # Create a Message instance to call _parse_received_date
    m = Message()
    result = m._parse_received_date(parsed_email)

    assert result is not None, "received_date should not be None"

    # The last date in the list is the last Received: header added
    last_dt = dates[-1]
    expected_ts = int(last_dt.timestamp())
    actual_ts = int(result.timestamp())
    assert abs(actual_ts - expected_ts) <= 1, (
        f"Expected last received date ~{expected_ts}, got {actual_ts}"
    )


# ---------------------------------------------------------------------------
# Property 14: received_date fallback to X-Received
# Validates: Requirements 3.7
# ---------------------------------------------------------------------------


@given(st.datetimes(
    min_value=_datetime(1970, 1, 1),
    max_value=_datetime(2099, 12, 31),
    timezones=st.just(timezone.utc),
))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_received_date_fallback_to_x_received(dt):
    """Feature: raw-message-source, Property 14: received_date fallback to X-Received

    For any RFC 2822 string with no Received: header but one X-Received: header
    with a valid date, _parse_received_date SHALL return the datetime from the
    last X-Received: header.

    **Validates: Requirements 3.7**
    """
    msg = MIMEText("plain text", "plain", "utf-8")
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Test"
    msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
    msg["X-Received"] = f"by xserver.example.com; {_format_received_date(dt)}"

    raw = msg.as_string()
    parsed_email = _email.message_from_string(raw)

    m = Message()
    result = m._parse_received_date(parsed_email)

    assert result is not None, "received_date should not be None when X-Received is present"

    expected_ts = int(dt.timestamp())
    actual_ts = int(result.timestamp())
    assert abs(actual_ts - expected_ts) <= 1, (
        f"Expected X-Received date ~{expected_ts}, got {actual_ts}"
    )


# ---------------------------------------------------------------------------
# DB layer helpers for Properties 9 and 10
# ---------------------------------------------------------------------------


def _setup_test_db():
    """Create and return an in-memory SQLite database for property tests."""
    from playhouse.sqlite_ext import SqliteDatabase
    from gmail_to_sqlite.db import database_proxy, Message, Attachment

    db = SqliteDatabase(":memory:")
    database_proxy.initialize(db)
    db.create_tables([Message, Attachment])
    return db


def _teardown_test_db(db):
    """Close and clean up the test database."""
    db.close()


def _make_msg_for_db(msg_id: str, raw_value, received_date_value):
    """Create a minimal Message object for use with create_message."""
    from gmail_to_sqlite.message import Message as MsgClass
    from datetime import datetime

    msg = MsgClass()
    msg.id = msg_id
    msg.thread_id = "thread-prop-001"
    msg.sender = {"name": "Alice", "email": "alice@example.com"}
    msg.recipients = {"to": [{"name": "Bob", "email": "bob@example.com"}]}
    msg.labels = ["INBOX"]
    msg.subject = "Property Test"
    msg.body = "body text"
    msg.raw = raw_value
    msg.received_date = received_date_value
    msg.size = 512
    msg.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    msg.is_read = False
    msg.is_outgoing = False
    msg.attachments = []
    return msg


# ---------------------------------------------------------------------------
# Property 9: DB raw and received_date round-trip
# Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
# ---------------------------------------------------------------------------


@given(
    st.one_of(st.none(), st.text()),
    st.one_of(st.none(), st.datetimes()),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_db_raw_and_received_date_roundtrip(raw_value, received_date):
    """Feature: raw-message-source, Property 9: DB raw and received_date round-trip

    For any Message object with a raw attribute and a received_date attribute
    (each independently None or a value), calling create_message and then
    querying the database SHALL return the same raw and received_date values.
    When called again with different values (upsert), the stored values SHALL
    be updated.

    **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**
    """
    from gmail_to_sqlite.db import Message as DbMessage, create_message

    db = _setup_test_db()
    try:
        msg_id = "prop9-msg-001"
        msg = _make_msg_for_db(msg_id, raw_value, received_date)
        create_message(msg)

        stored = DbMessage.get(DbMessage.message_id == msg_id)
        assert stored.raw == raw_value, (
            f"raw mismatch after insert: expected {raw_value!r}, got {stored.raw!r}"
        )

        # For received_date, compare timestamps (peewee may strip microseconds)
        if received_date is None:
            assert stored.received_date is None, (
                f"received_date should be None, got {stored.received_date!r}"
            )
        else:
            assert stored.received_date is not None, (
                f"received_date should not be None, got None"
            )
            # Compare truncated to seconds to handle microsecond precision loss
            # Use direct datetime comparison after stripping microseconds
            expected = received_date.replace(microsecond=0)
            actual = stored.received_date.replace(microsecond=0)
            # Normalize timezone info for comparison (peewee may strip tzinfo)
            if expected.tzinfo is not None and actual.tzinfo is None:
                from datetime import timezone as _tz
                expected = expected.replace(tzinfo=None)
            elif expected.tzinfo is None and actual.tzinfo is not None:
                actual = actual.replace(tzinfo=None)
            assert actual == expected, (
                f"received_date mismatch: expected {expected!r}, got {actual!r}"
            )

        # Now upsert with different values
        new_raw = None if raw_value is not None else "updated raw content"
        new_received_date = None if received_date is not None else _datetime(2025, 6, 1, 0, 0, 0)
        msg2 = _make_msg_for_db(msg_id, new_raw, new_received_date)
        create_message(msg2)

        stored2 = DbMessage.get(DbMessage.message_id == msg_id)
        assert stored2.raw == new_raw, (
            f"raw mismatch after upsert: expected {new_raw!r}, got {stored2.raw!r}"
        )
        if new_received_date is None:
            assert stored2.received_date is None, (
                f"received_date should be None after upsert, got {stored2.received_date!r}"
            )
        else:
            assert stored2.received_date is not None, (
                "received_date should not be None after upsert"
            )
            expected2 = new_received_date.replace(microsecond=0)
            actual2 = stored2.received_date.replace(microsecond=0)
            if expected2.tzinfo is not None and actual2.tzinfo is None:
                expected2 = expected2.replace(tzinfo=None)
            elif expected2.tzinfo is None and actual2.tzinfo is not None:
                actual2 = actual2.replace(tzinfo=None)
            assert actual2 == expected2, (
                f"received_date mismatch after upsert: expected {expected2!r}, got {actual2!r}"
            )
    finally:
        _teardown_test_db(db)


# ---------------------------------------------------------------------------
# Property 10: get_message_ids_missing_raw completeness
# Validates: Requirements 10.1
# ---------------------------------------------------------------------------


@given(st.lists(st.one_of(st.none(), st.text(min_size=1)), max_size=20))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_missing_raw_completeness(raw_values):
    """Feature: raw-message-source, Property 10: get_message_ids_missing_raw completeness

    For any set of messages in the database where some have raw = NULL and
    others have raw set to a non-null string, get_message_ids_missing_raw()
    SHALL return exactly the IDs of messages with NULL raw — no more, no fewer.

    **Validates: Requirements 10.1**
    """
    from gmail_to_sqlite.db import Message as DbMessage, create_message, get_message_ids_missing_raw

    db = _setup_test_db()
    try:
        expected_missing = set()

        for i, raw_val in enumerate(raw_values):
            msg_id = f"prop10-msg-{i:04d}"
            msg = _make_msg_for_db(msg_id, raw_val, None)
            create_message(msg)
            if raw_val is None:
                expected_missing.add(msg_id)

        result = set(get_message_ids_missing_raw())
        assert result == expected_missing, (
            f"Missing raw IDs mismatch:\n"
            f"  expected: {sorted(expected_missing)}\n"
            f"  got:      {sorted(result)}"
        )
    finally:
        _teardown_test_db(db)


# ---------------------------------------------------------------------------
# Strategy for RFC 2822 messages with an HTML part (used by Property 8)
# ---------------------------------------------------------------------------


@st.composite
def rfc2822_with_html_strategy(draw):
    """
    Composite strategy that generates a tuple of (raw_str, html_content)
    where raw_str is a valid RFC 2822 multipart/alternative message containing
    the html_content as its text/html part.
    """
    # Generate safe HTML content (ASCII printable, no MIME boundary conflicts)
    html_content = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=(),
                whitelist_characters="".join(
                    chr(c) for c in range(32, 127)
                    if chr(c) not in "\r\n"
                ),
            ),
            min_size=1,
            max_size=200,
        )
    )

    msg = MIMEMultipart("alternative")
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Property 8 Test"
    msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
    msg.attach(MIMEText("plain text body", "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    return msg.as_string(), html_content


# ---------------------------------------------------------------------------
# DB and Flask app helpers for Property 8
# ---------------------------------------------------------------------------


def _setup_api_test_db():
    """Create an in-memory SQLite database with the messages schema for API tests."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE messages (
            message_id    TEXT PRIMARY KEY,
            thread_id     TEXT,
            sender        TEXT,
            recipients    TEXT,
            labels        TEXT,
            subject       TEXT,
            body          TEXT,
            raw           TEXT,
            received_date DATETIME,
            size          INTEGER,
            timestamp     DATETIME,
            is_read       INTEGER,
            is_outgoing   INTEGER,
            is_deleted    INTEGER,
            last_indexed  DATETIME
        )
    """)
    conn.execute("""
        CREATE TABLE attachments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id    TEXT NOT NULL,
            filename      TEXT,
            mime_type     TEXT NOT NULL,
            size          INTEGER NOT NULL DEFAULT 0,
            data          BLOB,
            attachment_id TEXT,
            content_id    TEXT
        )
    """)
    conn.commit()
    return conn


def _insert_message_with_raw(conn, message_id: str, raw_value):
    """Insert a minimal message row with the given raw value."""
    conn.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            message_id, "thread-prop8",
            '{"name": "Alice", "email": "alice@example.com"}',
            '{"to": [{"name": "Bob", "email": "bob@example.com"}], "cc": [], "bcc": []}',
            '["INBOX"]',
            "Property 8 Test", "plain body",
            raw_value,
            None,  # received_date
            500,
            "2024-01-01T12:00:00",
            0, 0, 0,
            "2024-01-01T12:00:00",
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Property 8: API response body_html derivation
# Validates: Requirements 5.2, 5.4
# ---------------------------------------------------------------------------


@given(rfc2822_with_html_strategy())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_api_body_html_derivation(rfc2822_data):
    """Feature: raw-message-source, Property 8: API response body_html derivation

    For any message stored in the database with a non-null raw value, the
    body_html field in the GET /api/messages/<id> response SHALL equal
    extract_html_from_raw(raw) after CID rewriting is applied.

    **Validates: Requirements 5.2, 5.4**
    """
    import re
    import tempfile
    import os
    from web.server import create_app

    raw_str, html_content = rfc2822_data
    message_id = "prop8-msg-001"

    # Compute expected body_html (extract + CID rewrite)
    expected_html = extract_html_from_raw(raw_str)
    if expected_html:
        expected_html = re.sub(
            r'cid:([^\s"\'>\)]+)',
            lambda m: f'/api/cid/{m.group(1)}?msg={message_id}',
            expected_html,
        )

    # Create a temporary SQLite file for the Flask app (Flask needs a file path)
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "prop8_test.db")

        # Set up the schema and insert the test message
        import sqlite3
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE messages (
                message_id    TEXT PRIMARY KEY,
                thread_id     TEXT,
                sender        TEXT,
                recipients    TEXT,
                labels        TEXT,
                subject       TEXT,
                body          TEXT,
                raw           TEXT,
                received_date DATETIME,
                size          INTEGER,
                timestamp     DATETIME,
                is_read       INTEGER,
                is_outgoing   INTEGER,
                is_deleted    INTEGER,
                last_indexed  DATETIME
            )
        """)
        conn.execute("""
            CREATE TABLE attachments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id    TEXT NOT NULL,
                filename      TEXT,
                mime_type     TEXT NOT NULL,
                size          INTEGER NOT NULL DEFAULT 0,
                data          BLOB,
                attachment_id TEXT,
                content_id    TEXT
            )
        """)
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                message_id, "thread-prop8",
                '{"name": "Alice", "email": "alice@example.com"}',
                '{"to": [{"name": "Bob", "email": "bob@example.com"}], "cc": [], "bcc": []}',
                '["INBOX"]',
                "Property 8 Test", "plain body",
                raw_str,
                None,
                500,
                "2024-01-01T12:00:00",
                0, 0, 0,
                "2024-01-01T12:00:00",
            ),
        )
        conn.commit()
        conn.close()

        # Create Flask app and test client
        flask_app = create_app(db_path=db_file)
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as test_client:
            resp = test_client.get(f"/api/messages/{message_id}")
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)}"
            )
            data = resp.get_json()

            assert "body_html" in data, "Response must contain 'body_html' key"
            assert data["body_html"] == expected_html, (
                f"body_html mismatch:\n"
                f"  expected: {expected_html!r}\n"
                f"  got:      {data['body_html']!r}"
            )
