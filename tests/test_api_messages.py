"""Unit tests for API server changes — Task 7.2.

Tests for:
- GET /api/messages/<id> returns body_html derived from raw
- returns body_html: null when raw is NULL
- returns raw field in response
- returns raw: null when raw is NULL
- CID rewriting applied to derived body_html
- DETAIL_FIELDS contains raw and not body_html

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 11.1, 11.2, 11.3
"""

import sqlite3
import tempfile
import textwrap

import pytest

from web.server import create_app
from web.api.messages import DETAIL_FIELDS, SUMMARY_FIELDS


# ---------------------------------------------------------------------------
# DB setup helpers
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
    raw          TEXT,
    size         INTEGER,
    timestamp    DATETIME,
    is_read      INTEGER,
    is_outgoing  INTEGER,
    is_deleted   INTEGER,
    last_indexed DATETIME
)
"""


# A minimal RFC 2822 multipart/alternative message with an HTML part
_MULTIPART_RAW = textwrap.dedent("""\
    MIME-Version: 1.0
    From: sender@example.com
    To: recipient@example.com
    Subject: Test message
    Date: Mon, 01 Jan 2024 12:00:00 +0000
    Content-Type: multipart/alternative; boundary="boundary123"

    --boundary123
    Content-Type: text/plain; charset="utf-8"

    Hello in plain text
    --boundary123
    Content-Type: text/html; charset="utf-8"

    <html><body><p>Hello in <b>HTML</b></p></body></html>
    --boundary123--
""")

# A raw message with a CID reference in the HTML part
_CID_RAW = textwrap.dedent("""\
    MIME-Version: 1.0
    From: sender@example.com
    To: recipient@example.com
    Subject: CID test
    Date: Mon, 01 Jan 2024 12:00:00 +0000
    Content-Type: multipart/alternative; boundary="cidboundary"

    --cidboundary
    Content-Type: text/plain; charset="utf-8"

    See attached image
    --cidboundary
    Content-Type: text/html; charset="utf-8"

    <html><body><img src="cid:image001@example.com"></body></html>
    --cidboundary--
""")

# A plain-text-only raw message (no HTML part)
_PLAIN_ONLY_RAW = textwrap.dedent("""\
    MIME-Version: 1.0
    From: sender@example.com
    To: recipient@example.com
    Subject: Plain only
    Date: Mon, 01 Jan 2024 12:00:00 +0000
    Content-Type: text/plain; charset="utf-8"

    Just plain text, no HTML.
""")


def _seed_db(path: str) -> None:
    """Create and seed the messages table in the SQLite file at *path*."""
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)

    _INSERT = (
        "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, "
        "subject, body, raw, size, timestamp, is_read, is_outgoing, is_deleted, last_indexed) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )

    # Message with a multipart raw (has HTML part)
    conn.execute(_INSERT, (
        "msg_with_raw", "thread1",
        '{"name": "Alice", "email": "alice@example.com"}',
        '{"to": [{"name": "Bob", "email": "bob@example.com"}], "cc": [], "bcc": []}',
        '["INBOX"]',
        "Test message", "Hello in plain text",
        _MULTIPART_RAW, 500, "2024-01-10T10:00:00", 0, 0, 0, "2024-01-10T10:00:00",
    ))

    # Message with NULL raw
    conn.execute(_INSERT, (
        "msg_null_raw", "thread2",
        '{"name": "Bob", "email": "bob@example.com"}',
        '{"to": [{"name": "Alice", "email": "alice@example.com"}], "cc": [], "bcc": []}',
        '["INBOX"]',
        "No raw", "Plain body",
        None, 200, "2024-01-09T09:00:00", 1, 0, 0, "2024-01-09T09:00:00",
    ))

    # Message with CID reference in HTML
    conn.execute(_INSERT, (
        "msg_cid", "thread3",
        '{"name": "Charlie", "email": "charlie@example.com"}',
        '{"to": [{"name": "Alice", "email": "alice@example.com"}], "cc": [], "bcc": []}',
        '["INBOX"]',
        "CID test", "See attached image",
        _CID_RAW, 300, "2024-01-08T08:00:00", 0, 0, 0, "2024-01-08T08:00:00",
    ))

    # Message with plain-text-only raw (no HTML part)
    conn.execute(_INSERT, (
        "msg_plain_raw", "thread4",
        '{"name": "Dave", "email": "dave@example.com"}',
        '{"to": [{"name": "Alice", "email": "alice@example.com"}], "cc": [], "bcc": []}',
        '["INBOX"]',
        "Plain only", "Just plain text, no HTML.",
        _PLAIN_ONLY_RAW, 150, "2024-01-07T07:00:00", 0, 0, 0, "2024-01-07T07:00:00",
    ))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return the path to a seeded temporary SQLite database."""
    path = str(tmp_path / "test_api_messages.db")
    _seed_db(path)
    return path


@pytest.fixture
def app(db_path):
    """Create a Flask app backed by the seeded temporary database."""
    flask_app = create_app(db_path=db_path)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Tests for DETAIL_FIELDS and SUMMARY_FIELDS constants
# ---------------------------------------------------------------------------

class TestFieldConstants:
    def test_detail_fields_contains_raw(self):
        """DETAIL_FIELDS must contain 'raw'."""
        assert "raw" in DETAIL_FIELDS

    def test_detail_fields_does_not_contain_body_html(self):
        """DETAIL_FIELDS must NOT contain 'body_html' (it is derived, not stored)."""
        assert "body_html" not in DETAIL_FIELDS

# ---------------------------------------------------------------------------
# Tests for GET /api/messages/<id> — body_html derivation
# ---------------------------------------------------------------------------

class TestBodyHtmlDerivation:
    def test_returns_body_html_derived_from_raw(self, client):
        """GET /api/messages/<id> returns body_html derived from raw."""
        resp = client.get("/api/messages/msg_with_raw")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "body_html" in data
        # The HTML part of _MULTIPART_RAW contains <html><body>...
        assert data["body_html"] is not None
        assert "<html>" in data["body_html"] or "<html" in data["body_html"]
        assert "Hello in" in data["body_html"]

    def test_returns_body_html_null_when_raw_is_null(self, client):
        """GET /api/messages/<id> returns body_html: null when raw is NULL."""
        resp = client.get("/api/messages/msg_null_raw")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "body_html" in data
        assert data["body_html"] is None

    def test_returns_body_html_null_when_raw_has_no_html_part(self, client):
        """GET /api/messages/<id> returns body_html: null when raw has no HTML part."""
        resp = client.get("/api/messages/msg_plain_raw")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "body_html" in data
        assert data["body_html"] is None

    def test_body_html_matches_extract_html_from_raw(self, client):
        """body_html in response equals extract_html_from_raw(raw) after CID rewriting."""
        from gmail_to_sqlite.message import extract_html_from_raw
        import re

        resp = client.get("/api/messages/msg_with_raw")
        assert resp.status_code == 200
        data = resp.get_json()

        # Compute expected value
        expected_html = extract_html_from_raw(_MULTIPART_RAW)
        if expected_html:
            expected_html = re.sub(
                r'cid:([^\s"\'>\)]+)',
                lambda m: f'/api/cid/{m.group(1)}?msg=msg_with_raw',
                expected_html,
            )

        assert data["body_html"] == expected_html


# ---------------------------------------------------------------------------
# Tests for GET /api/messages/<id> — raw field
# ---------------------------------------------------------------------------

class TestRawField:
    def test_returns_raw_field_in_response(self, client):
        """GET /api/messages/<id> returns the raw field in the response."""
        resp = client.get("/api/messages/msg_with_raw")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "raw" in data
        assert data["raw"] is not None
        assert "Content-Type: multipart/alternative" in data["raw"]

    def test_returns_raw_null_when_raw_is_null(self, client):
        """GET /api/messages/<id> returns raw: null when raw is NULL."""
        resp = client.get("/api/messages/msg_null_raw")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "raw" in data
        assert data["raw"] is None

# ---------------------------------------------------------------------------
# Tests for CID rewriting applied to derived body_html
# ---------------------------------------------------------------------------

class TestCIDRewriting:
    def test_cid_rewriting_applied_to_derived_body_html(self, client):
        """CID rewriting is applied to body_html derived from raw."""
        resp = client.get("/api/messages/msg_cid")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "body_html" in data
        assert data["body_html"] is not None
        # The cid: reference should be rewritten to /api/cid/...?msg=...
        assert "cid:" not in data["body_html"], (
            "CID reference was not rewritten in body_html"
        )
        assert "/api/cid/image001@example.com?msg=msg_cid" in data["body_html"], (
            "Expected rewritten CID URL not found in body_html"
        )
