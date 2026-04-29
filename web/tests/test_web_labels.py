"""Unit tests for GET /api/labels."""

import sqlite3

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
    body_html    TEXT,
    size         INTEGER,
    timestamp    DATETIME,
    is_read      INTEGER,
    is_outgoing  INTEGER,
    is_deleted   INTEGER,
    last_indexed DATETIME
)
"""

SEED_ROWS = [
    # Non-deleted messages with various labels
    (
        "msg1", "thread1",
        '{"name": "Alice", "email": "alice@example.com"}',
        '{"to": ["bob@example.com"], "cc": [], "bcc": []}',
        '["INBOX", "Work"]',
        "Hello Bob", "Hi there", 100,
        "2024-01-10T10:00:00", 0, 0, 0,
    ),
    (
        "msg2", "thread2",
        '{"name": "Bob", "email": "bob@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["INBOX", "SENT"]',
        "Re: Hello", "Fine thanks", 80,
        "2024-01-09T09:00:00", 1, 0, 0,
    ),
    (
        "msg3", "thread3",
        '{"name": "Charlie", "email": "charlie@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["Work", "Projects"]',
        "Project update", "Here is the update", 120,
        "2024-01-08T08:00:00", 1, 0, 0,
    ),
    # Deleted message — its labels should NOT appear in the response
    (
        "msg4", "thread4",
        '{"name": "Dave", "email": "dave@example.com"}',
        '{"to": ["alice@example.com"], "cc": [], "bcc": []}',
        '["TRASH", "DeletedOnly"]',
        "Deleted message", "This is deleted", 50,
        "2024-01-07T07:00:00", 0, 0, 1,
    ),
]


def _seed_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TABLE_SQL)
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?,NULL,?,?,?,?,?,NULL)",
        SEED_ROWS,
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_labels.db")
    _seed_db(path)
    return path


@pytest.fixture
def app(db_path):
    flask_app = create_app(db_path=db_path)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetLabels:
    def test_returns_200(self, client):
        resp = client.get("/api/labels")
        assert resp.status_code == 200

    def test_returns_json_array(self, client):
        resp = client.get("/api/labels")
        data = resp.get_json()
        assert isinstance(data, list)

    def test_excludes_labels_from_deleted_messages(self, client):
        resp = client.get("/api/labels")
        data = resp.get_json()
        assert "TRASH" not in data
        assert "DeletedOnly" not in data

    def test_includes_labels_from_non_deleted_messages(self, client):
        resp = client.get("/api/labels")
        data = resp.get_json()
        assert "INBOX" in data
        assert "Work" in data
        assert "SENT" in data
        assert "Projects" in data

    def test_deduplication(self, client):
        # "INBOX" appears in msg1 and msg2; "Work" appears in msg1 and msg3
        resp = client.get("/api/labels")
        data = resp.get_json()
        assert data.count("INBOX") == 1
        assert data.count("Work") == 1

    def test_sorted_alphabetically(self, client):
        resp = client.get("/api/labels")
        data = resp.get_json()
        assert data == sorted(data)

    def test_exact_label_set(self, client):
        resp = client.get("/api/labels")
        data = resp.get_json()
        # From non-deleted messages: INBOX, SENT, Work, Projects
        assert set(data) == {"INBOX", "SENT", "Work", "Projects"}

    def test_empty_db_returns_empty_list(self, tmp_path):
        """When there are no non-deleted messages, return an empty array."""
        path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(path)
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
        conn.close()

        flask_app = create_app(db_path=path)
        flask_app.config["TESTING"] = True
        c = flask_app.test_client()
        resp = c.get("/api/labels")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_all_deleted_returns_empty_list(self, tmp_path):
        """When all messages are deleted, return an empty array."""
        path = str(tmp_path / "all_deleted.db")
        conn = sqlite3.connect(path)
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,NULL,?,?,?,?,?,NULL)",
            ("m1", "t1", "{}", "{}", '["INBOX"]', "s", "b", 1, "2024-01-01", 0, 0, 1),
        )
        conn.commit()
        conn.close()

        flask_app = create_app(db_path=path)
        flask_app.config["TESTING"] = True
        c = flask_app.test_client()
        resp = c.get("/api/labels")
        assert resp.status_code == 200
        assert resp.get_json() == []
