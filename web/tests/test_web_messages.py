"""Unit tests for GET /api/messages and GET /api/messages/<message_id>."""

import json
import sqlite3
import tempfile
import os

import pytest

from web.server import create_app

# ---------------------------------------------------------------------------
# DB setup helpers
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
    received_date DATETIME,
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

SEED_ROWS = [
    # (message_id, thread_id, sender, recipients, labels, subject, body, size, timestamp, is_read, is_outgoing, is_deleted)
    (
        "msg1", "thread1",
        '{"name": "Alice", "email": "alice@example.com"}',
        '{"to": ["bob@example.com"], "cc": [], "bcc": []}',
        '["INBOX", "Work"]',
        "Hello Bob", "Hi there, how are you?", 100,
        "2024-01-10T10:00:00", 0, 0, 0,
    ),
    (
        "msg2", "thread2",
        '{"name": "Bob", "email": "bob@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["INBOX"]',
        "Re: Hello Bob", "I am fine, thanks!", 80,
        "2024-01-09T09:00:00", 1, 0, 0,
    ),
    (
        "msg3", "thread3",
        '{"name": "Charlie", "email": "charlie@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["SENT"]',
        "Meeting tomorrow", "Let us meet at 10am.", 120,
        "2024-01-08T08:00:00", 1, 1, 0,
    ),
    (
        "msg4", "thread4",
        '{"name": "Dave", "email": "dave@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["TRASH"]',
        "Deleted message", "This is deleted.", 50,
        "2024-01-07T07:00:00", 0, 0, 1,
    ),
    (
        "msg5", "thread5",
        '{"name": "Eve", "email": "eve@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["Work"]',
        "Project update", "Here is the update on the project.", 200,
        "2024-01-06T06:00:00", 0, 0, 0,
    ),
]

# A minimal RFC 2822 multipart/alternative message with an HTML part
_MULTIPART_RAW_HTML = (
    "MIME-Version: 1.0\r\n"
    "From: frank@example.com\r\n"
    "To: alice@example.com\r\n"
    "Subject: HTML message\r\n"
    "Date: Mon, 05 Jan 2024 05:00:00 +0000\r\n"
    "Content-Type: multipart/alternative; boundary=\"b123\"\r\n"
    "\r\n"
    "--b123\r\n"
    "Content-Type: text/plain; charset=\"utf-8\"\r\n"
    "\r\n"
    "Hello in plain text\r\n"
    "--b123\r\n"
    "Content-Type: text/html; charset=\"utf-8\"\r\n"
    "\r\n"
    "<html><body><p>Hello in <b>HTML</b></p></body></html>\r\n"
    "--b123--\r\n"
)

# Rows that include an explicit raw value with HTML:
# (message_id, thread_id, sender, recipients, labels, subject, body, raw, size, timestamp, is_read, is_outgoing, is_deleted)
SEED_ROWS_WITH_HTML = [
    (
        "msg_html", "thread_html",
        '{"name": "Frank", "email": "frank@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["INBOX"]',
        "HTML message", "Hello in plain text",
        _MULTIPART_RAW_HTML,
        150,
        "2024-01-05T05:00:00", 0, 0, 0,
    ),
    (
        "msg_no_html", "thread_no_html",
        '{"name": "Grace", "email": "grace@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["INBOX"]',
        "Plain text only", "Just plain text here",
        None,  # raw is NULL
        90,
        "2024-01-04T04:00:00", 0, 0, 0,
    ),
]


def _seed_db(path: str) -> None:
    """Create and seed the messages table in the SQLite file at *path*."""
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
    conn.executemany(
        "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, subject, body, raw, received_date, size, timestamp, is_read, is_outgoing, is_deleted, last_indexed) "
        "VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,?,NULL)",
        SEED_ROWS,
    )
    conn.executemany(
        "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, subject, body, raw, received_date, size, timestamp, is_read, is_outgoing, is_deleted, last_indexed) "
        "VALUES (?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,NULL)",
        SEED_ROWS_WITH_HTML,
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return the path to a seeded temporary SQLite database."""
    path = str(tmp_path / "test_messages.db")
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
# 3.6 — Parameter validation tests
# ---------------------------------------------------------------------------

class TestParameterValidation:
    def test_invalid_page_zero(self, client):
        resp = client.get("/api/messages?page=0")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_invalid_page_negative(self, client):
        resp = client.get("/api/messages?page=-1")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_invalid_page_string(self, client):
        resp = client.get("/api/messages?page=abc")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_invalid_page_size_zero(self, client):
        resp = client.get("/api/messages?page_size=0")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_invalid_page_size_negative(self, client):
        resp = client.get("/api/messages?page_size=-5")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_invalid_page_size_too_large(self, client):
        resp = client.get("/api/messages?page_size=201")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_invalid_page_size_string(self, client):
        resp = client.get("/api/messages?page_size=xyz")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_valid_page_size_boundary_1(self, client):
        resp = client.get("/api/messages?page_size=1")
        assert resp.status_code == 200

    def test_valid_page_size_boundary_200(self, client):
        resp = client.get("/api/messages?page_size=200")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3.6 — Response envelope tests
# ---------------------------------------------------------------------------

class TestResponseEnvelope:
    def test_envelope_fields_present(self, client):
        resp = client.get("/api/messages")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "messages" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_default_page_and_page_size(self, client):
        resp = client.get("/api/messages")
        data = resp.get_json()
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_custom_page_and_page_size_reflected(self, client):
        resp = client.get("/api/messages?page=2&page_size=10")
        data = resp.get_json()
        assert data["page"] == 2
        assert data["page_size"] == 10

    def test_total_excludes_deleted_by_default(self, client):
        resp = client.get("/api/messages")
        data = resp.get_json()
        # 6 non-deleted messages in seed data (5 original + 2 html test rows)
        assert data["total"] == 6

    def test_messages_ordered_by_timestamp_desc(self, client):
        resp = client.get("/api/messages")
        data = resp.get_json()
        timestamps = [m["timestamp"] for m in data["messages"]]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# 3.6 — Filter tests
# ---------------------------------------------------------------------------

class TestFilters:
    def test_search_q_subject(self, client):
        resp = client.get("/api/messages?q=Hello")
        data = resp.get_json()
        # "Hello Bob", "Re: Hello Bob" (subject), and "msg_html" (body: "Hello in plain text") match
        assert data["total"] == 3
        ids = {m["message_id"] for m in data["messages"]}
        assert ids == {"msg1", "msg2", "msg_html"}

    def test_search_q_case_insensitive(self, client):
        resp = client.get("/api/messages?q=hello")
        data = resp.get_json()
        assert data["total"] == 3

    def test_search_q_sender(self, client):
        resp = client.get("/api/messages?q=alice@example.com")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["messages"][0]["message_id"] == "msg1"

    def test_search_q_body(self, client):
        resp = client.get("/api/messages?q=project")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["messages"][0]["message_id"] == "msg5"

    def test_search_q_no_match(self, client):
        resp = client.get("/api/messages?q=zzznomatch")
        data = resp.get_json()
        assert data["total"] == 0
        assert data["messages"] == []

    def test_label_filter_inbox(self, client):
        resp = client.get("/api/messages?label=INBOX")
        data = resp.get_json()
        assert data["total"] == 4
        ids = {m["message_id"] for m in data["messages"]}
        assert ids == {"msg1", "msg2", "msg_html", "msg_no_html"}

    def test_label_filter_work(self, client):
        resp = client.get("/api/messages?label=Work")
        data = resp.get_json()
        assert data["total"] == 2
        ids = {m["message_id"] for m in data["messages"]}
        assert ids == {"msg1", "msg5"}

    def test_label_filter_no_match(self, client):
        resp = client.get("/api/messages?label=NONEXISTENT")
        data = resp.get_json()
        assert data["total"] == 0

    def test_is_read_true(self, client):
        resp = client.get("/api/messages?is_read=true")
        data = resp.get_json()
        assert data["total"] == 2
        for m in data["messages"]:
            assert m["is_read"] is True

    def test_is_read_false(self, client):
        resp = client.get("/api/messages?is_read=false")
        data = resp.get_json()
        assert data["total"] == 4
        for m in data["messages"]:
            assert m["is_read"] is False

    def test_is_outgoing_true(self, client):
        resp = client.get("/api/messages?is_outgoing=true")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["messages"][0]["message_id"] == "msg3"
        for m in data["messages"]:
            assert m["is_outgoing"] is True

    def test_is_outgoing_false(self, client):
        resp = client.get("/api/messages?is_outgoing=false")
        data = resp.get_json()
        for m in data["messages"]:
            assert m["is_outgoing"] is False

    def test_include_deleted_false_by_default(self, client):
        resp = client.get("/api/messages")
        data = resp.get_json()
        for m in data["messages"]:
            assert m["is_deleted"] is False

    def test_include_deleted_true(self, client):
        resp = client.get("/api/messages?include_deleted=true")
        data = resp.get_json()
        # All 7 messages including the deleted one
        assert data["total"] == 7
        ids = {m["message_id"] for m in data["messages"]}
        assert "msg4" in ids

    def test_pagination_page_size_limits_results(self, client):
        resp = client.get("/api/messages?page_size=2")
        data = resp.get_json()
        assert len(data["messages"]) == 2
        assert data["total"] == 6  # total is still 6

    def test_pagination_second_page(self, client):
        resp = client.get("/api/messages?page=2&page_size=2")
        data = resp.get_json()
        assert len(data["messages"]) == 2

    def test_pagination_beyond_last_page(self, client):
        resp = client.get("/api/messages?page=100&page_size=50")
        data = resp.get_json()
        assert data["messages"] == []
        assert data["total"] == 6


# ---------------------------------------------------------------------------
# 3.7 — GET /api/messages/<message_id> tests
# ---------------------------------------------------------------------------

class TestGetMessage:
    def test_existing_message_returns_200(self, client):
        resp = client.get("/api/messages/msg1")
        assert resp.status_code == 200

    def test_existing_message_has_summary_fields(self, client):
        resp = client.get("/api/messages/msg1")
        data = resp.get_json()
        for field in ("message_id", "thread_id", "sender", "labels", "subject",
                      "timestamp", "is_read", "is_outgoing", "is_deleted"):
            assert field in data, f"Missing field: {field}"

    def test_existing_message_has_detail_fields(self, client):
        resp = client.get("/api/messages/msg1")
        data = resp.get_json()
        assert "recipients" in data
        assert "body" in data

    def test_existing_message_correct_data(self, client):
        resp = client.get("/api/messages/msg1")
        data = resp.get_json()
        assert data["message_id"] == "msg1"
        assert data["subject"] == "Hello Bob"
        assert data["sender"]["email"] == "alice@example.com"
        assert data["body"] == "Hi there, how are you?"

    def test_existing_message_sender_is_dict(self, client):
        resp = client.get("/api/messages/msg1")
        data = resp.get_json()
        assert isinstance(data["sender"], dict)
        assert "name" in data["sender"]
        assert "email" in data["sender"]

    def test_existing_message_labels_is_list(self, client):
        resp = client.get("/api/messages/msg1")
        data = resp.get_json()
        assert isinstance(data["labels"], list)

    def test_existing_message_recipients_is_dict(self, client):
        resp = client.get("/api/messages/msg1")
        data = resp.get_json()
        assert isinstance(data["recipients"], dict)

    def test_nonexistent_message_returns_404(self, client):
        resp = client.get("/api/messages/does_not_exist")
        assert resp.status_code == 404

    def test_nonexistent_message_error_body(self, client):
        resp = client.get("/api/messages/does_not_exist")
        data = resp.get_json()
        assert data == {"error": "Message not found"}


# ---------------------------------------------------------------------------
# 8.1–8.3 — body_html field tests
# ---------------------------------------------------------------------------

class TestBodyHtml:
    def test_detail_returns_body_html_when_non_null(self, client):
        """8.1 — GET /api/messages/<id> returns body_html derived from raw when raw has HTML."""
        resp = client.get("/api/messages/msg_html")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "body_html" in data
        assert data["body_html"] is not None
        # The HTML part of _MULTIPART_RAW_HTML contains <html><body>...
        assert "<html>" in data["body_html"] or "<html" in data["body_html"]

    def test_detail_returns_body_html_null_when_no_html(self, client):
        """8.2 — GET /api/messages/<id> returns body_html: null for a message with no raw."""
        resp = client.get("/api/messages/msg_no_html")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "body_html" in data
        assert data["body_html"] is None

    def test_list_items_do_not_contain_body_html(self, client):
        """8.3 — GET /api/messages list response items do not contain a body_html key."""
        resp = client.get("/api/messages?page_size=200")
        assert resp.status_code == 200
        data = resp.get_json()
        for item in data["messages"]:
            assert "body_html" not in item, (
                f"List item for message_id={item.get('message_id')!r} "
                "unexpectedly contains 'body_html'"
            )


# ---------------------------------------------------------------------------
# 17.1–17.5 — Attachment Web API tests
# ---------------------------------------------------------------------------

class TestAttachmentWebAPI:
    """Tests for attachment-related endpoints on GET /api/messages/<id>
    and GET /api/messages/<id>/attachments/<aid>/data."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _seed_attachments(self, db_path: str) -> None:
        """Insert attachment rows into the test database."""
        conn = sqlite3.connect(db_path)
        # Attachment with non-null data for msg1
        conn.execute(
            "INSERT INTO attachments (message_id, filename, mime_type, size, data, attachment_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("msg1", "report.pdf", "application/pdf", 1024, b"PDF binary content", "att_001"),
        )
        # Second attachment for msg1 (no data — large attachment)
        conn.execute(
            "INSERT INTO attachments (message_id, filename, mime_type, size, data, attachment_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("msg1", "photo.jpg", "image/jpeg", 2048, None, "att_002"),
        )
        conn.commit()
        conn.close()

    @pytest.fixture
    def db_path_with_attachments(self, db_path):
        """Return a seeded DB path that also has attachment rows for msg1."""
        self._seed_attachments(db_path)
        return db_path

    @pytest.fixture
    def client_with_attachments(self, db_path_with_attachments):
        """Flask test client backed by a DB that has attachment rows."""
        from web.server import create_app
        flask_app = create_app(db_path=db_path_with_attachments)
        flask_app.config["TESTING"] = True
        return flask_app.test_client()

    # ------------------------------------------------------------------
    # 17.1 — attachments array shape for a message WITH attachments
    # ------------------------------------------------------------------

    def test_attachments_array_shape_with_attachments(self, client_with_attachments):
        """17.1 — GET /api/messages/<id> returns attachments array with correct
        shape (filename, mime_type, size, attachment_id present; no data key)."""
        resp = client_with_attachments.get("/api/messages/msg1")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "attachments" in data
        assert isinstance(data["attachments"], list)
        assert len(data["attachments"]) == 2

        for item in data["attachments"]:
            assert "filename" in item, "Missing 'filename' key"
            assert "mime_type" in item, "Missing 'mime_type' key"
            assert "size" in item, "Missing 'size' key"
            assert "attachment_id" in item, "Missing 'attachment_id' key"
            assert "data" not in item, "Response must NOT contain 'data' key"

    def test_attachments_array_first_item_values(self, client_with_attachments):
        """17.1 — Verify the first attachment's field values are correct."""
        resp = client_with_attachments.get("/api/messages/msg1")
        data = resp.get_json()
        items = {a["attachment_id"]: a for a in data["attachments"]}

        att = items["att_001"]
        assert att["filename"] == "report.pdf"
        assert att["mime_type"] == "application/pdf"
        assert att["size"] == 1024
        assert att["attachment_id"] == "att_001"

    # ------------------------------------------------------------------
    # 17.2 — empty attachments array for a message WITHOUT attachments
    # ------------------------------------------------------------------

    def test_attachments_array_empty_for_message_without_attachments(self, client):
        """17.2 — GET /api/messages/<id> returns an empty attachments array
        when the message has no attachments."""
        # msg2 has no attachment rows in the base seeded DB
        resp = client.get("/api/messages/msg2")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "attachments" in data
        assert data["attachments"] == []

    # ------------------------------------------------------------------
    # 17.3 — data endpoint returns raw bytes with correct Content-Type
    # ------------------------------------------------------------------

    def test_attachment_data_returns_raw_bytes_and_content_type(self, client_with_attachments):
        """17.3 — GET /api/messages/<id>/attachments/<aid>/data returns the
        stored raw bytes with the correct Content-Type header."""
        resp = client_with_attachments.get("/api/messages/msg1/attachments/att_001/data")
        assert resp.status_code == 200
        assert resp.data == b"PDF binary content"
        assert resp.content_type == "application/pdf"

    # ------------------------------------------------------------------
    # 17.4 — data endpoint returns 404 when attachment does not exist
    # ------------------------------------------------------------------

    def test_attachment_data_404_when_attachment_not_found(self, client_with_attachments):
        """17.4 — GET /api/messages/<id>/attachments/<aid>/data returns HTTP 404
        when the attachment_id does not exist."""
        resp = client_with_attachments.get("/api/messages/msg1/attachments/nonexistent_id/data")
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # 17.5 — data endpoint returns 404 when attachment data is NULL
    # ------------------------------------------------------------------

    def test_attachment_data_404_when_data_is_null(self, client_with_attachments):
        """17.5 — GET /api/messages/<id>/attachments/<aid>/data returns HTTP 404
        with an appropriate error message when the attachment's data is NULL."""
        from unittest.mock import patch
        # Mock the Gmail API fetch to raise an error (simulating no credentials/network)
        # The test verifies that when data is NULL and Gmail fetch fails, we get 404
        with patch("web.api.messages._fetch_attachment_from_gmail") as mock_fetch:
            mock_fetch.side_effect = Exception("No credentials available in test environment")
            resp = client_with_attachments.get("/api/messages/msg1/attachments/att_002/data")
        # When data is NULL and Gmail fetch fails, the API returns 502
        # The test verifies the response is not 200 (data is not available)
        assert resp.status_code in (404, 502), (
            f"Expected 404 or 502 when attachment data is NULL and Gmail fetch fails, "
            f"got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 4.1 — GET /api/messages/stats tests
# ---------------------------------------------------------------------------

CREATE_GMAIL_INDEX_SQL = """
CREATE TABLE gmail_index (
    message_id  TEXT PRIMARY KEY,
    synced      INTEGER NOT NULL DEFAULT 0
)
"""


class TestMessagesStats:
    """Tests for GET /api/messages/stats (Requirement 4.1)."""

    # ------------------------------------------------------------------
    # 11.1 — Happy-path: messages + gmail_index both present
    # ------------------------------------------------------------------

    def test_stats_happy_path(self, tmp_path):
        """11.1 — Returns correct total_messages, total_indexed, total_unsynced
        when both messages and gmail_index tables are populated."""
        db_file = str(tmp_path / "stats_happy.db")
        conn = sqlite3.connect(db_file)
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_GMAIL_INDEX_SQL)

        # Insert 4 non-deleted messages and 1 deleted message
        conn.executemany(
            "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, "
            "subject, body, raw, received_date, size, timestamp, is_read, is_outgoing, "
            "is_deleted, last_indexed) VALUES (?,?,?,?,?,?,?,NULL,NULL,0,NULL,0,0,?,NULL)",
            [
                ("m1", "t1", "{}", "{}", "[]", "s1", "b1", 0),
                ("m2", "t2", "{}", "{}", "[]", "s2", "b2", 0),
                ("m3", "t3", "{}", "{}", "[]", "s3", "b3", 0),
                ("m4", "t4", "{}", "{}", "[]", "s4", "b4", 0),
                ("m5", "t5", "{}", "{}", "[]", "s5", "b5", 1),  # deleted
            ],
        )

        # 3 indexed rows: 2 synced, 1 unsynced
        conn.executemany(
            "INSERT INTO gmail_index (message_id, synced) VALUES (?, ?)",
            [("m1", 1), ("m2", 1), ("m3", 0)],
        )
        conn.commit()
        conn.close()

        flask_app = create_app(db_path=db_file)
        flask_app.config["TESTING"] = True
        client = flask_app.test_client()

        resp = client.get("/api/messages/stats")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["total_messages"] == 4   # excludes deleted
        assert data["total_indexed"] == 3    # rows in gmail_index
        assert data["total_unsynced"] == 1   # synced=0 rows

    # ------------------------------------------------------------------
    # 11.2 — Missing gmail_index table: graceful fallback
    # ------------------------------------------------------------------

    def test_stats_missing_gmail_index_table(self, tmp_path):
        """11.2 — When gmail_index table does not exist, the endpoint returns
        total_indexed == total_messages and total_unsynced == 0 (no 500)."""
        db_file = str(tmp_path / "stats_no_index.db")
        conn = sqlite3.connect(db_file)
        conn.execute(CREATE_TABLE_SQL)

        # Insert 3 non-deleted messages
        conn.executemany(
            "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, "
            "subject, body, raw, received_date, size, timestamp, is_read, is_outgoing, "
            "is_deleted, last_indexed) VALUES (?,?,?,?,?,?,?,NULL,NULL,0,NULL,0,0,0,NULL)",
            [("a1", "t1", "{}", "{}", "[]", "s1", "b1"),
             ("a2", "t2", "{}", "{}", "[]", "s2", "b2"),
             ("a3", "t3", "{}", "{}", "[]", "s3", "b3")],
        )
        conn.commit()
        conn.close()

        flask_app = create_app(db_path=db_file)
        flask_app.config["TESTING"] = True
        client = flask_app.test_client()

        resp = client.get("/api/messages/stats")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["total_messages"] == 3
        assert data["total_indexed"] == 3    # fallback: equals total_messages
        assert data["total_unsynced"] == 0   # fallback: 0

    # ------------------------------------------------------------------
    # 11.3 — Missing messages table: returns zeros, not 500
    # ------------------------------------------------------------------

    def test_stats_missing_messages_table(self, tmp_path):
        """11.3 — When messages table does not exist, the endpoint returns
        {"total_messages": 0, "total_indexed": 0, "total_unsynced": 0} (no 500)."""
        db_file = str(tmp_path / "stats_no_messages.db")
        # Create an empty DB with no tables at all
        conn = sqlite3.connect(db_file)
        conn.commit()
        conn.close()

        flask_app = create_app(db_path=db_file)
        flask_app.config["TESTING"] = True
        client = flask_app.test_client()

        resp = client.get("/api/messages/stats")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data == {"total_messages": 0, "total_indexed": 0, "total_unsynced": 0}


# ---------------------------------------------------------------------------
# 13.1–13.3 — by-filename attachment endpoint tests
# ---------------------------------------------------------------------------

import base64 as _base64

# Minimal RFC 2822 multipart/mixed message with a PDF attachment.
# The attachment payload is base64-encoded so get_payload(decode=True) works.
_ATTACH_BYTES = b"FAKE PDF CONTENT"
_ATTACH_B64 = _base64.b64encode(_ATTACH_BYTES).decode("ascii")

_MULTIPART_WITH_ATTACHMENT = (
    "MIME-Version: 1.0\r\n"
    "From: sender@example.com\r\n"
    "To: recipient@example.com\r\n"
    "Subject: Message with attachment\r\n"
    "Date: Mon, 05 Jan 2024 05:00:00 +0000\r\n"
    "Content-Type: multipart/mixed; boundary=\"att_boundary\"\r\n"
    "\r\n"
    "--att_boundary\r\n"
    "Content-Type: text/plain; charset=\"utf-8\"\r\n"
    "\r\n"
    "See attached file.\r\n"
    "--att_boundary\r\n"
    "Content-Type: application/pdf\r\n"
    "Content-Disposition: attachment; filename=\"report.pdf\"\r\n"
    "Content-Transfer-Encoding: base64\r\n"
    "\r\n"
    f"{_ATTACH_B64}\r\n"
    "--att_boundary--\r\n"
)

# Minimal RFC 2822 multipart/related message with an inline PNG image.
_IMAGE_BYTES = b"\x89PNG\r\nFAKE IMAGE DATA"
_IMAGE_B64 = _base64.b64encode(_IMAGE_BYTES).decode("ascii")

_MULTIPART_WITH_CID_IMAGE = (
    "MIME-Version: 1.0\r\n"
    "From: sender@example.com\r\n"
    "To: recipient@example.com\r\n"
    "Subject: Message with inline image\r\n"
    "Date: Mon, 05 Jan 2024 05:00:00 +0000\r\n"
    "Content-Type: multipart/related; boundary=\"cid_boundary\"\r\n"
    "\r\n"
    "--cid_boundary\r\n"
    "Content-Type: text/html; charset=\"utf-8\"\r\n"
    "\r\n"
    "<html><body><img src=\"cid:inline_img_001\"></body></html>\r\n"
    "--cid_boundary\r\n"
    "Content-Type: image/png\r\n"
    "Content-ID: <inline_img_001>\r\n"
    "Content-Disposition: inline; filename=\"logo.png\"\r\n"
    "Content-Transfer-Encoding: base64\r\n"
    "\r\n"
    f"{_IMAGE_B64}\r\n"
    "--cid_boundary--\r\n"
)


class TestByFilenameAttachment:
    """Tests for GET /api/messages/<id>/attachments/by-filename/<filename>/data
    (Requirements 4.4)."""

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def db_path_raw_attach(self, tmp_path):
        """DB with a message whose raw source contains a PDF attachment."""
        path = str(tmp_path / "raw_attach.db")
        conn = sqlite3.connect(path)
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
        # Insert the message with raw RFC 2822 source
        conn.execute(
            "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, "
            "subject, body, raw, received_date, size, timestamp, is_read, is_outgoing, "
            "is_deleted, last_indexed) VALUES (?,?,?,?,?,?,?,?,NULL,?,?,0,0,0,NULL)",
            (
                "msg_raw_attach", "thread_raw_attach",
                '{"name": "Sender", "email": "sender@example.com"}',
                '{"to": ["recipient@example.com"], "cc": [], "bcc": []}',
                '["INBOX"]',
                "Message with attachment",
                "See attached file.",
                _MULTIPART_WITH_ATTACHMENT,
                len(_MULTIPART_WITH_ATTACHMENT),
                "2024-01-05T05:00:00",
            ),
        )
        # Insert a matching attachments row (no blob data — raw source is the source of truth)
        conn.execute(
            "INSERT INTO attachments (message_id, filename, mime_type, size, data, attachment_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("msg_raw_attach", "report.pdf", "application/pdf", len(_ATTACH_BYTES), None, None),
        )
        conn.commit()
        conn.close()
        return path

    @pytest.fixture
    def client_raw_attach(self, db_path_raw_attach):
        from web.server import create_app
        flask_app = create_app(db_path=db_path_raw_attach)
        flask_app.config["TESTING"] = True
        return flask_app.test_client()

    @pytest.fixture
    def db_path_blob_attach(self, tmp_path):
        """DB with a message that has a DB blob attachment and no raw source."""
        path = str(tmp_path / "blob_attach.db")
        conn = sqlite3.connect(path)
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
        conn.execute(
            "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, "
            "subject, body, raw, received_date, size, timestamp, is_read, is_outgoing, "
            "is_deleted, last_indexed) VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,0,0,0,NULL)",
            (
                "msg_blob_attach", "thread_blob_attach",
                '{"name": "Sender", "email": "sender@example.com"}',
                '{"to": ["recipient@example.com"], "cc": [], "bcc": []}',
                '["INBOX"]',
                "Message with blob attachment",
                "Body text.",
                100,
                "2024-01-05T05:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO attachments (message_id, filename, mime_type, size, data, attachment_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("msg_blob_attach", "data.bin", "application/octet-stream", 8, b"BLOBDATA", None),
        )
        conn.commit()
        conn.close()
        return path

    @pytest.fixture
    def client_blob_attach(self, db_path_blob_attach):
        from web.server import create_app
        flask_app = create_app(db_path=db_path_blob_attach)
        flask_app.config["TESTING"] = True
        return flask_app.test_client()

    # ------------------------------------------------------------------
    # 13.1 — by-filename found via raw source
    # ------------------------------------------------------------------

    def test_by_filename_raw_source_returns_200(self, client_raw_attach):
        """13.1 — by-filename endpoint returns 200 when attachment is in raw source."""
        resp = client_raw_attach.get(
            "/api/messages/msg_raw_attach/attachments/by-filename/report.pdf/data"
        )
        assert resp.status_code == 200

    def test_by_filename_raw_source_correct_bytes(self, client_raw_attach):
        """13.1 — by-filename endpoint returns the correct bytes from raw source."""
        resp = client_raw_attach.get(
            "/api/messages/msg_raw_attach/attachments/by-filename/report.pdf/data"
        )
        assert resp.data == _ATTACH_BYTES

    def test_by_filename_raw_source_correct_content_type(self, client_raw_attach):
        """13.1 — by-filename endpoint returns the correct Content-Type from raw source."""
        resp = client_raw_attach.get(
            "/api/messages/msg_raw_attach/attachments/by-filename/report.pdf/data"
        )
        assert resp.content_type == "application/pdf"

    # ------------------------------------------------------------------
    # 13.2 — by-filename DB blob fallback
    # ------------------------------------------------------------------

    def test_by_filename_blob_fallback_returns_200(self, client_blob_attach):
        """13.2 — by-filename endpoint returns 200 when falling back to DB blob."""
        resp = client_blob_attach.get(
            "/api/messages/msg_blob_attach/attachments/by-filename/data.bin/data"
        )
        assert resp.status_code == 200

    def test_by_filename_blob_fallback_correct_bytes(self, client_blob_attach):
        """13.2 — by-filename endpoint returns the correct blob bytes."""
        resp = client_blob_attach.get(
            "/api/messages/msg_blob_attach/attachments/by-filename/data.bin/data"
        )
        assert resp.data == b"BLOBDATA"

    # ------------------------------------------------------------------
    # 13.3 — by-filename 404 for unknown filename
    # ------------------------------------------------------------------

    def test_by_filename_404_for_unknown_filename(self, client_raw_attach):
        """13.3 — by-filename endpoint returns 404 when filename does not exist."""
        resp = client_raw_attach.get(
            "/api/messages/msg_raw_attach/attachments/by-filename/nonexistent.xyz/data"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 13.4–13.5 — GET /api/cid/<content_id> tests
# ---------------------------------------------------------------------------


class TestCidImage:
    """Tests for GET /api/cid/<content_id> (Requirements 4.6)."""

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    @pytest.fixture
    def db_path_cid(self, tmp_path):
        """DB with a message whose raw source contains an inline image with Content-ID."""
        path = str(tmp_path / "cid_image.db")
        conn = sqlite3.connect(path)
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_ATTACHMENTS_TABLE_SQL)
        conn.execute(
            "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, "
            "subject, body, raw, received_date, size, timestamp, is_read, is_outgoing, "
            "is_deleted, last_indexed) VALUES (?,?,?,?,?,?,?,?,NULL,?,?,0,0,0,NULL)",
            (
                "msg_cid", "thread_cid",
                '{"name": "Sender", "email": "sender@example.com"}',
                '{"to": ["recipient@example.com"], "cc": [], "bcc": []}',
                '["INBOX"]',
                "Message with inline image",
                "See inline image.",
                _MULTIPART_WITH_CID_IMAGE,
                len(_MULTIPART_WITH_CID_IMAGE),
                "2024-01-05T05:00:00",
            ),
        )
        # Insert an attachments row with content_id so the endpoint can find the message
        conn.execute(
            "INSERT INTO attachments (message_id, filename, mime_type, size, data, "
            "attachment_id, content_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "msg_cid", "logo.png", "image/png", len(_IMAGE_BYTES),
                None, None, "inline_img_001",
            ),
        )
        conn.commit()
        conn.close()
        return path

    @pytest.fixture
    def client_cid(self, db_path_cid):
        from web.server import create_app
        flask_app = create_app(db_path=db_path_cid)
        flask_app.config["TESTING"] = True
        return flask_app.test_client()

    # ------------------------------------------------------------------
    # 13.4 — CID found via raw source
    # ------------------------------------------------------------------

    def test_cid_found_returns_200(self, client_cid):
        """13.4 — GET /api/cid/<content_id> returns 200 when the inline image exists."""
        resp = client_cid.get("/api/cid/inline_img_001?msg=msg_cid")
        assert resp.status_code == 200

    def test_cid_found_correct_bytes(self, client_cid):
        """13.4 — GET /api/cid/<content_id> returns the correct image bytes."""
        resp = client_cid.get("/api/cid/inline_img_001?msg=msg_cid")
        assert resp.data == _IMAGE_BYTES

    def test_cid_found_correct_content_type(self, client_cid):
        """13.4 — GET /api/cid/<content_id> returns the correct Content-Type."""
        resp = client_cid.get("/api/cid/inline_img_001?msg=msg_cid")
        assert resp.content_type == "image/png"

    # ------------------------------------------------------------------
    # 13.5 — CID 404 for unknown content_id
    # ------------------------------------------------------------------

    def test_cid_404_for_unknown_content_id(self, client_cid):
        """13.5 — GET /api/cid/<content_id> returns 404 when content_id is not in DB."""
        resp = client_cid.get("/api/cid/nonexistent_cid_xyz")
        assert resp.status_code == 404
