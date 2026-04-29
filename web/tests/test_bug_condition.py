"""Bug condition exploration tests for the missing-db-ux bugfix.

These tests are EXPECTED TO FAIL on unfixed code.
Failure confirms the bug exists: both endpoints return HTTP 500 with the raw
SQLite error string "no such table: messages" instead of HTTP 503 with a
friendly message.

DO NOT fix the code or the assertions when these tests fail.

Validates: Requirements 1.1, 1.2
"""

import sqlite3
import pytest

from web.server import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def no_table_db(tmp_path):
    """A SQLite file that exists on disk but contains NO tables.

    This is the canonical trigger for the bug: connecting to this DB and
    querying the messages table raises:
        sqlite3.OperationalError: no such table: messages
    """
    db_file = tmp_path / "no_table.db"
    # Create the file by opening a connection, but do NOT create any tables.
    conn = sqlite3.connect(str(db_file))
    conn.close()
    return str(db_file)


@pytest.fixture
def no_table_app(no_table_db):
    """Flask app backed by the no-table database."""
    flask_app = create_app(db_path=no_table_db)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def no_table_client(no_table_app):
    return no_table_app.test_client()


# ---------------------------------------------------------------------------
# Bug condition exploration tests
# These tests encode the EXPECTED (fixed) behavior.
# They FAIL on unfixed code, proving the bug exists.
# ---------------------------------------------------------------------------

class TestBugConditionListMessages:
    """GET /api/messages on a no-table DB should return 503, not 500."""

    def test_list_messages_no_table_not_500(self, no_table_client):
        """GET /api/messages on a no-table DB must NOT return HTTP 500.

        On unfixed code this returns HTTP 500 — test fails, confirming the bug.
        """
        resp = no_table_client.get("/api/messages")
        assert resp.status_code != 500, (
            f"BUG CONFIRMED: GET /api/messages returned HTTP 500 "
            f"(body: {resp.get_data(as_text=True)!r})"
        )

    def test_list_messages_no_table_no_raw_sqlite_error(self, no_table_client):
        """GET /api/messages on a no-table DB must NOT expose the raw SQLite error.

        On unfixed code the body contains "no such table: messages" — test
        fails, confirming the bug.
        """
        resp = no_table_client.get("/api/messages")
        body = resp.get_data(as_text=True)
        assert "no such table" not in body, (
            f"BUG CONFIRMED: GET /api/messages exposed raw SQLite error "
            f"(body: {body!r})"
        )

    def test_list_messages_no_table_returns_503(self, no_table_client):
        """GET /api/messages on a no-table DB should return HTTP 503.

        On unfixed code this returns HTTP 500 — test fails, confirming the bug.
        """
        resp = no_table_client.get("/api/messages")
        assert resp.status_code == 503, (
            f"BUG CONFIRMED: GET /api/messages returned HTTP {resp.status_code} "
            f"instead of 503 (body: {resp.get_data(as_text=True)!r})"
        )

    def test_list_messages_no_table_friendly_message_contains_sync(self, no_table_client):
        """GET /api/messages on a no-table DB should return a message mentioning 'sync'.

        On unfixed code the error body is the raw SQLite string — test fails,
        confirming the bug.
        """
        resp = no_table_client.get("/api/messages")
        data = resp.get_json()
        assert data is not None, "Response body is not valid JSON"
        error_msg = data.get("error", "")
        assert "sync" in error_msg.lower(), (
            f"BUG CONFIRMED: GET /api/messages error message does not mention "
            f"'sync' (error: {error_msg!r})"
        )


class TestBugConditionGetMessage:
    """GET /api/messages/<id> on a no-table DB should return 503, not 500."""

    def test_get_message_no_table_not_500(self, no_table_client):
        """GET /api/messages/<id> on a no-table DB must NOT return HTTP 500.

        On unfixed code this returns HTTP 500 — test fails, confirming the bug.
        """
        resp = no_table_client.get("/api/messages/any_id")
        assert resp.status_code != 500, (
            f"BUG CONFIRMED: GET /api/messages/any_id returned HTTP 500 "
            f"(body: {resp.get_data(as_text=True)!r})"
        )

    def test_get_message_no_table_no_raw_sqlite_error(self, no_table_client):
        """GET /api/messages/<id> on a no-table DB must NOT expose the raw SQLite error.

        On unfixed code the body contains "no such table: messages" — test
        fails, confirming the bug.
        """
        resp = no_table_client.get("/api/messages/any_id")
        body = resp.get_data(as_text=True)
        assert "no such table" not in body, (
            f"BUG CONFIRMED: GET /api/messages/any_id exposed raw SQLite error "
            f"(body: {body!r})"
        )

    def test_get_message_no_table_returns_503(self, no_table_client):
        """GET /api/messages/<id> on a no-table DB should return HTTP 503.

        On unfixed code this returns HTTP 500 — test fails, confirming the bug.
        """
        resp = no_table_client.get("/api/messages/any_id")
        assert resp.status_code == 503, (
            f"BUG CONFIRMED: GET /api/messages/any_id returned HTTP {resp.status_code} "
            f"instead of 503 (body: {resp.get_data(as_text=True)!r})"
        )

    def test_get_message_no_table_friendly_message_contains_sync(self, no_table_client):
        """GET /api/messages/<id> on a no-table DB should return a message mentioning 'sync'.

        On unfixed code the error body is the raw SQLite string — test fails,
        confirming the bug.
        """
        resp = no_table_client.get("/api/messages/any_id")
        data = resp.get_json()
        assert data is not None, "Response body is not valid JSON"
        error_msg = data.get("error", "")
        assert "sync" in error_msg.lower(), (
            f"BUG CONFIRMED: GET /api/messages/any_id error message does not "
            f"mention 'sync' (error: {error_msg!r})"
        )
