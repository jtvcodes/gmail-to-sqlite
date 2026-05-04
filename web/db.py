import sqlite3

from flask import current_app, g

# ---------------------------------------------------------------------------
# Indexes that speed up the common list/sort/filter queries.
# All use IF NOT EXISTS so they are safe to run on every startup — SQLite
# skips creation silently when the index already exists.
# ---------------------------------------------------------------------------

_INDEX_STATEMENTS = [
    # Most queries filter out deleted rows first; this alone cuts the working
    # set dramatically for databases where few messages are deleted.
    "CREATE INDEX IF NOT EXISTS idx_messages_is_deleted "
    "ON messages (is_deleted)",

    # Every page load sorts by timestamp.  The composite index covers the
    # most common query pattern (non-deleted rows in timestamp order) so
    # SQLite can satisfy ORDER BY + WHERE is_deleted=0 with a single index
    # scan instead of a full table scan + sort.
    "CREATE INDEX IF NOT EXISTS idx_messages_deleted_timestamp "
    "ON messages (is_deleted, timestamp)",

    # Standalone timestamp index used when other filters are active and the
    # query planner cannot use the composite index for the ORDER BY.
    "CREATE INDEX IF NOT EXISTS idx_messages_timestamp "
    "ON messages (timestamp)",

    # Boolean filter columns used by the is_read / is_outgoing filter bar.
    "CREATE INDEX IF NOT EXISTS idx_messages_is_read "
    "ON messages (is_read)",

    "CREATE INDEX IF NOT EXISTS idx_messages_is_outgoing "
    "ON messages (is_outgoing)",

    # content_id lookup used when resolving cid: inline images in message bodies.
    "CREATE INDEX IF NOT EXISTS idx_attachments_content_id "
    "ON attachments (content_id)",
]


def ensure_indexes(db_path: str) -> None:
    """Create performance indexes on the messages database if they don't exist.

    Called once at application startup.  Uses a direct connection (not the
    per-request ``get_db`` connection) so it runs outside any request context.
    Safe to call repeatedly — all statements use IF NOT EXISTS.
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            for stmt in _INDEX_STATEMENTS:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    # Table may not exist yet (fresh install before first sync).
                    # Indexes will be created on the next startup after sync.
                    pass
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Never crash the server over a missing index.
        pass


def get_db() -> sqlite3.Connection:
    """Return the SQLite connection for the current application context.

    Opens a new connection if one does not already exist for this context.
    The connection uses ``sqlite3.Row`` as the row factory so columns are
    accessible by name, and ``PARSE_DECLTYPES`` so that declared column types
    (e.g. DATETIME) are converted automatically.
    """
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DB_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception: BaseException | None = None) -> None:
    """Close the SQLite connection at the end of the application context."""
    db = g.pop("db", None)
    if db is not None:
        db.close()
