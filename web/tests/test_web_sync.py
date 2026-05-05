"""Unit tests for GET /api/sync/status (Requirement 4.2)."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from web.server import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return the path to a minimal temporary SQLite database."""
    path = str(tmp_path / "test_sync.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE messages (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT, sender TEXT, recipients TEXT, labels TEXT,
            subject TEXT, body TEXT, raw TEXT, DATETIME,
            size INTEGER, timestamp DATETIME, is_read INTEGER,
            is_outgoing INTEGER, is_deleted INTEGER, last_indexed DATETIME
        )"""
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def app(db_path):
    """Create a Flask app backed by the temporary database."""
    flask_app = create_app(db_path=db_path)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# 12.1 — No sync running
# ---------------------------------------------------------------------------

class TestSyncStatusNoSession:
    """4.2 — GET /api/sync/status returns {"running": false} when no sync is active."""

    def test_no_sync_running_returns_false(self, client):
        """12.1 — When no sync session is active, response is {"running": false}."""
        with patch("web.api.sync._session", None):
            resp = client.get("/api/sync/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"running": False}


# ---------------------------------------------------------------------------
# 12.2 — Sync in progress
# ---------------------------------------------------------------------------

class TestSyncStatusInProgress:
    """4.2 — GET /api/sync/status returns {"running": true, "mode": <mode>}
    when a sync session is active."""

    def _make_running_session(self, mode: str) -> MagicMock:
        """Return a mock SyncSession that reports itself as running."""
        session = MagicMock()
        session.running = True
        session.mode = mode
        session.lines = []
        session._lock = MagicMock()
        session._lock.__enter__ = MagicMock(return_value=None)
        session._lock.__exit__ = MagicMock(return_value=False)
        return session

    def test_sync_in_progress_returns_true_with_mode(self, client):
        """12.2 — When a sync session is running, response includes running=true and mode."""
        mock_session = self._make_running_session("delta")

        with patch("web.api.sync._session", mock_session):
            resp = client.get("/api/sync/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["running"] is True
        assert data["mode"] == "delta"

    def test_sync_in_progress_mode_force(self, client):
        """12.2 — Mode is correctly reflected for 'force' sync."""
        mock_session = self._make_running_session("force")

        with patch("web.api.sync._session", mock_session):
            resp = client.get("/api/sync/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["running"] is True
        assert data["mode"] == "force"

    def test_sync_in_progress_mode_missing(self, client):
        """12.2 — Mode is correctly reflected for 'missing' sync."""
        mock_session = self._make_running_session("missing")

        with patch("web.api.sync._session", mock_session):
            resp = client.get("/api/sync/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["running"] is True
        assert data["mode"] == "missing"
