import sqlite3
import threading
import time

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

    # The UI sorts by COALESCE(received_date, timestamp). SQLite cannot use a
    # plain column index for an expression, so we add a generated column that
    # pre-computes the value and index that instead.  The column is VIRTUAL
    # (not stored) so it costs no extra disk space.
    "ALTER TABLE messages ADD COLUMN sort_date TEXT "
    "GENERATED ALWAYS AS (COALESCE(received_date, timestamp)) VIRTUAL",

    # Covering index for the default page load: non-deleted rows in sort_date
    # order.  SQLite can satisfy WHERE is_deleted=0 ORDER BY sort_date with a
    # single index scan — no filesort needed.
    "CREATE INDEX IF NOT EXISTS idx_messages_deleted_sort_date "
    "ON messages (is_deleted, sort_date)",

    # Descending variant so both sort directions use an index scan.
    "CREATE INDEX IF NOT EXISTS idx_messages_deleted_sort_date_desc "
    "ON messages (is_deleted, sort_date DESC)",

    # Standalone sort_date index used when other filters are active.
    "CREATE INDEX IF NOT EXISTS idx_messages_sort_date "
    "ON messages (sort_date)",

    # Legacy timestamp indexes kept for any direct timestamp queries.
    "CREATE INDEX IF NOT EXISTS idx_messages_deleted_timestamp "
    "ON messages (is_deleted, timestamp)",

    "CREATE INDEX IF NOT EXISTS idx_messages_timestamp "
    "ON messages (timestamp)",

    # Boolean filter columns used by the is_read / is_outgoing filter bar.
    "CREATE INDEX IF NOT EXISTS idx_messages_is_read "
    "ON messages (is_read)",

    "CREATE INDEX IF NOT EXISTS idx_messages_is_outgoing "
    "ON messages (is_outgoing)",

    # Covering index for the has_attachments EXISTS subquery.
    # SQLite can resolve the subquery with an index-only scan on this index.
    "CREATE INDEX IF NOT EXISTS idx_attachments_message_id_covering "
    "ON attachments (message_id, filename, attachment_id, mime_type)",

    # content_id lookup used when resolving cid: inline images in message bodies.
    "CREATE INDEX IF NOT EXISTS idx_attachments_content_id "
    "ON attachments (content_id)",
]

# ---------------------------------------------------------------------------
# Module-level cache: whether the sort_date generated column exists.
# Checked once per process lifetime — the column never disappears after being
# added, so caching indefinitely is safe.
# ---------------------------------------------------------------------------
_sort_date_available: bool | None = None
_sort_date_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Module-level count cache: avoids re-running COUNT(*) on every page load.
# Entries expire after COUNT_CACHE_TTL seconds so the UI stays fresh after
# a sync completes.
# ---------------------------------------------------------------------------
COUNT_CACHE_TTL = 5  # seconds
_count_cache: dict[tuple, tuple[int, float]] = {}
_count_cache_lock = threading.Lock()


def ensure_indexes(db_path: str) -> None:
    """Create performance indexes on the messages database if they don't exist.

    Called once at application startup and again after sync completes.
    Safe to call repeatedly — all statements use IF NOT EXISTS.
    Also resets the sort_date availability cache so the next request
    re-checks after a sync that may have created the table.
    """
    global _sort_date_available
    try:
        conn = sqlite3.connect(db_path)
        try:
            for stmt in _INDEX_STATEMENTS:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    # Silently skip:
                    #  - Table/column doesn't exist yet (fresh install before first sync)
                    #  - Generated column already added (server restart)
                    #  - Index already exists (IF NOT EXISTS handles this, but belt-and-suspenders)
                    pass
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Never crash the server over a missing index.
        pass

    # Reset the cached value so the next request re-checks.
    with _sort_date_lock:
        _sort_date_available = None

    # Invalidate the count cache after a sync so totals are fresh.
    invalidate_count_cache()


def has_sort_date_column(conn: sqlite3.Connection) -> bool:
    """Return True if the messages table has the sort_date generated column.

    Generated columns have hidden=2 in pragma_table_xinfo but do NOT appear
    in pragma_table_info — so we must use table_xinfo here.

    The result is cached for the lifetime of the process — the column is
    never removed once added, so a single check is sufficient.
    """
    global _sort_date_available
    with _sort_date_lock:
        if _sort_date_available is not None:
            return _sort_date_available
        try:
            # table_xinfo includes generated (hidden=2) and virtual columns
            row = conn.execute(
                "SELECT 1 FROM pragma_table_xinfo('messages') WHERE name='sort_date'"
            ).fetchone()
            _sort_date_available = row is not None
            return _sort_date_available
        except Exception:
            # Older SQLite versions may not support table_xinfo — fall back
            try:
                row = conn.execute(
                    "SELECT 1 FROM pragma_table_info('messages') WHERE name='sort_date'"
                ).fetchone()
                _sort_date_available = row is not None
                return _sort_date_available
            except Exception:
                return False


def get_cached_count(db: sqlite3.Connection, sql: str, params: list) -> int:
    """Execute a COUNT query and cache the result for COUNT_CACHE_TTL seconds.

    This eliminates the full-table-scan COUNT(*) on every page load and
    pagination request. The cache is keyed on (sql, params) so different
    filter combinations are cached independently.
    """
    key = (sql, tuple(params))
    now = time.monotonic()
    with _count_cache_lock:
        entry = _count_cache.get(key)
        if entry is not None and now - entry[1] < COUNT_CACHE_TTL:
            return entry[0]
    # Run outside the lock to avoid blocking other threads during the query.
    count = db.execute(sql, params).fetchone()[0]
    with _count_cache_lock:
        _count_cache[key] = (count, time.monotonic())
    return count


def invalidate_count_cache() -> None:
    """Clear all cached COUNT results (call after sync completes)."""
    with _count_cache_lock:
        _count_cache.clear()


def prewarm_db(db_path: str) -> None:
    """Open a connection and run a warm-up query in a background thread.

    SQLite's page cache is per-connection. By running a query at startup we
    pull the most-accessed pages into the OS page cache so the first real
    request is fast.
    """
    def _warm():
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA cache_size=-32000")
            conn.execute("PRAGMA temp_store=MEMORY")
            # Warm the index pages used by the default page load.
            conn.execute(
                "SELECT COUNT(*) FROM messages WHERE is_deleted = 0"
            ).fetchone()
            conn.close()
        except Exception:
            pass  # DB may not exist yet — that's fine

    threading.Thread(target=_warm, daemon=True).start()


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
        # WAL mode allows concurrent reads without blocking writes, and a
        # larger page cache reduces disk I/O on repeated queries.
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA cache_size=-32000")   # ~32 MB
        g.db.execute("PRAGMA temp_store=MEMORY")
        g.db.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, faster than FULL
    return g.db


def close_db(exception: BaseException | None = None) -> None:
    """Close the SQLite connection at the end of the application context."""
    db = g.pop("db", None)
    if db is not None:
        db.close()
