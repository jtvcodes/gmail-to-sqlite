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
    message_id   TEXT PRIMARY KEY,
    thread_id    TEXT,
    sender       TEXT,
    recipients   TEXT,
    labels       TEXT,
    subject      TEXT,
    body         TEXT,
    size         INTEGER,
    timestamp    DATETIME,
    is_read      INTEGER,
    is_outgoing  INTEGER,
    is_deleted   INTEGER,
    last_indexed DATETIME
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


def _seed_db(path: str) -> None:
    """Create and seed the messages table in the SQLite file at *path*."""
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
        SEED_ROWS,
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
        # 4 non-deleted messages in seed data
        assert data["total"] == 4

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
        # "Hello Bob" and "Re: Hello Bob" both match
        assert data["total"] == 2
        ids = {m["message_id"] for m in data["messages"]}
        assert ids == {"msg1", "msg2"}

    def test_search_q_case_insensitive(self, client):
        resp = client.get("/api/messages?q=hello")
        data = resp.get_json()
        assert data["total"] == 2

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
        assert data["total"] == 2
        ids = {m["message_id"] for m in data["messages"]}
        assert ids == {"msg1", "msg2"}

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
        assert data["total"] == 2
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
        # All 5 messages including the deleted one
        assert data["total"] == 5
        ids = {m["message_id"] for m in data["messages"]}
        assert "msg4" in ids

    def test_pagination_page_size_limits_results(self, client):
        resp = client.get("/api/messages?page_size=2")
        data = resp.get_json()
        assert len(data["messages"]) == 2
        assert data["total"] == 4  # total is still 4

    def test_pagination_second_page(self, client):
        resp = client.get("/api/messages?page=2&page_size=2")
        data = resp.get_json()
        assert len(data["messages"]) == 2

    def test_pagination_beyond_last_page(self, client):
        resp = client.get("/api/messages?page=100&page_size=50")
        data = resp.get_json()
        assert data["messages"] == []
        assert data["total"] == 4


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
