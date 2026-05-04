import json
import logging
import os
import re
import sqlite3
import sys

from flask import Blueprint, current_app, jsonify, make_response, request

from web.db import get_db, has_sort_date_column, ensure_indexes, get_cached_count, invalidate_count_cache

# Module-level cache: whether the has_attachments stored column exists.
# Checked once per process — the column never disappears once added.
_has_attachments_col: bool | None = None
_has_attachments_col_lock = __import__("threading").Lock()


def _has_stored_attachments_col(db) -> bool:
    """Return True if messages table has a stored has_attachments column."""
    global _has_attachments_col
    with _has_attachments_col_lock:
        if _has_attachments_col is not None:
            return _has_attachments_col
        try:
            row = db.execute(
                "SELECT 1 FROM pragma_table_info('messages') WHERE name='has_attachments'"
            ).fetchone()
            _has_attachments_col = row is not None
            return _has_attachments_col
        except Exception:
            _has_attachments_col = False
            return False
from gmail_to_sqlite.message import extract_html_from_raw, extract_attachment_from_raw, extract_attachment_by_content_id

logger = logging.getLogger(__name__)

messages_bp = Blueprint("messages", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUMMARY_FIELDS = (
    "message_id",
    "thread_id",
    "sender",
    "labels",
    "subject",
    "timestamp",
    "received_date",
    "is_read",
    "is_outgoing",
    "is_deleted",
)

DETAIL_FIELDS = SUMMARY_FIELDS + ("recipients", "body", "raw")

BOOL_FIELDS = {"is_read", "is_outgoing", "is_deleted"}


def _is_missing_table_error(exc: Exception) -> bool:
    """Return True when exc is the specific 'no such table: messages' error."""
    return (
        isinstance(exc, sqlite3.OperationalError)
        and str(exc) == "no such table: messages"
    )


def _parse_bool_param(value: str, name: str):
    """Parse a 'true'/'false' query string value.

    Returns True, False, or raises ValueError with a descriptive message.
    """
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise ValueError(f"'{name}' must be 'true' or 'false'")


def _row_to_dict(row: sqlite3.Row, fields: tuple) -> dict:
    """Convert a sqlite3.Row to a plain dict, JSON-decoding JSON columns."""
    d = {}
    for field in fields:
        val = row[field]
        if field in ("sender", "recipients", "labels") and isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        elif field in BOOL_FIELDS and val is not None:
            val = bool(val)
        d[field] = val
    return d


# ---------------------------------------------------------------------------
# GET /api/messages
# ---------------------------------------------------------------------------

@messages_bp.route("/messages")
def list_messages():
    # --- pagination params ---
    try:
        page = int(request.args.get("page", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "'page' must be a positive integer"}), 400

    try:
        page_size = int(request.args.get("page_size", 50))
    except (ValueError, TypeError):
        return jsonify({"error": "'page_size' must be an integer between 1 and 200"}), 400

    if page < 1:
        return jsonify({"error": "'page' must be >= 1"}), 400
    if not (1 <= page_size <= 200):
        return jsonify({"error": "'page_size' must be between 1 and 200"}), 400

    # --- optional filters ---
    q = request.args.get("q", "").strip()
    label = request.args.get("label", "").strip()

    is_read = None
    if "is_read" in request.args:
        try:
            is_read = _parse_bool_param(request.args["is_read"], "is_read")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    is_outgoing = None
    if "is_outgoing" in request.args:
        try:
            is_outgoing = _parse_bool_param(request.args["is_outgoing"], "is_outgoing")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    include_deleted = False
    if "include_deleted" in request.args:
        try:
            include_deleted = _parse_bool_param(
                request.args["include_deleted"], "include_deleted"
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    # --- build WHERE clauses ---
    conditions = []
    params: list = []

    if not include_deleted:
        conditions.append("is_deleted = 0")

    if q:
        conditions.append(
            "(LOWER(subject) LIKE LOWER(?) OR LOWER(sender) LIKE LOWER(?) OR LOWER(body) LIKE LOWER(?) OR message_id = ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like, q])

    if label:
        # JSON array exact-match: look for the label as a JSON string element
        conditions.append(
            "EXISTS ("
            "  SELECT 1 FROM json_each(labels) WHERE json_each.value = ?"
            ")"
        )
        params.append(label)

    if is_read is not None:
        conditions.append("is_read = ?")
        params.append(1 if is_read else 0)

    if is_outgoing is not None:
        conditions.append("is_outgoing = ?")
        params.append(1 if is_outgoing else 0)

    where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # --- sort direction ---
    sort_dir = request.args.get("sort_dir", "desc").lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    try:
        db = get_db()
        # Use sort_date generated column if available, fall back to COALESCE expression.
        # sort_date may be missing on a fresh DB that was created after server start.
        if has_sort_date_column(db):
            order_sql = f"ORDER BY sort_date {sort_dir.upper()}"
        else:
            # Attempt to add the column + indexes now that the table exists
            ensure_indexes(current_app.config["DB_PATH"])
            order_sql = f"ORDER BY COALESCE(received_date, timestamp) {sort_dir.upper()}"
    except Exception:
        order_sql = f"ORDER BY COALESCE(received_date, timestamp) {sort_dir.upper()}"

    try:
        db = get_db()

        # total count (cached to avoid full-table scan on every page load)
        count_sql = f"SELECT COUNT(*) FROM messages {where_sql}"
        total = get_cached_count(db, count_sql, params)

        # paginated results
        offset = (page - 1) * page_size
        fields_sql = ", ".join(SUMMARY_FIELDS)

        # Use stored has_attachments column if available (avoids 50 correlated subqueries)
        if _has_stored_attachments_col(db):
            has_att_expr = "has_attachments"
        else:
            has_att_expr = (
                "EXISTS(SELECT 1 FROM attachments a WHERE a.message_id = messages.message_id "
                "  AND a.filename IS NOT NULL "
                "  AND a.mime_type NOT LIKE 'multipart/%')"
            )

        data_sql = (
            f"SELECT {fields_sql}, "
            f"{has_att_expr} AS has_attachments "
            f"FROM messages {where_sql} "
            f"{order_sql} "
            f"LIMIT ? OFFSET ?"
        )
        rows = db.execute(data_sql, params + [page_size, offset]).fetchall()

    except Exception as exc:
        print(f"Database error in list_messages: {exc}", file=sys.stderr)
        if _is_missing_table_error(exc):
            return jsonify({
                "error": "Database not ready — please run the sync command to populate the database."
            }), 503
        return jsonify({"error": str(exc)}), 500

    messages = [_row_to_dict(row, SUMMARY_FIELDS) for row in rows]
    for i, row in enumerate(rows):
        messages[i]["has_attachments"] = bool(row["has_attachments"])

    return jsonify(
        {
            "messages": messages,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# ---------------------------------------------------------------------------
# GET /api/messages/stats
# ---------------------------------------------------------------------------

@messages_bp.route("/messages/stats")
def messages_stats():
    """Return total message counts from the DB and gmail_index."""
    try:
        db = get_db()
        total_messages = db.execute(
            "SELECT COUNT(*) FROM messages WHERE is_deleted = 0"
        ).fetchone()[0]
        total_synced = total_messages  # messages table only has synced rows
        try:
            total_indexed = db.execute(
                "SELECT COUNT(*) FROM gmail_index"
            ).fetchone()[0]
            total_unsynced = db.execute(
                "SELECT COUNT(*) FROM gmail_index WHERE synced = 0"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            total_indexed = total_messages
            total_unsynced = 0
        return jsonify({
            "total_messages": total_messages,
            "total_indexed": total_indexed,
            "total_unsynced": total_unsynced,
        })
    except Exception as exc:
        if _is_missing_table_error(exc):
            return jsonify({"total_messages": 0, "total_indexed": 0, "total_unsynced": 0})
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /api/messages/<message_id>
# ---------------------------------------------------------------------------

@messages_bp.route("/messages/<message_id>")
def get_message(message_id: str):
    try:
        db = get_db()
        fields_sql = ", ".join(DETAIL_FIELDS)
        row = db.execute(
            f"SELECT {fields_sql} FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    except Exception as exc:
        print(f"Database error in get_message: {exc}", file=sys.stderr)
        if _is_missing_table_error(exc):
            return jsonify({
                "error": "Database not ready — please run the sync command to populate the database."
            }), 503
        return jsonify({"error": str(exc)}), 500

    if row is None:
        return jsonify({"error": "Message not found"}), 404

    msg_dict = _row_to_dict(row, DETAIL_FIELDS)

    # Query attachments (gracefully handle missing table)
    try:
        db = get_db()
        attachment_rows = db.execute(
            "SELECT filename, mime_type, size, attachment_id, content_id FROM attachments "
            "WHERE message_id = ? "
            "  AND filename IS NOT NULL "
            "  AND mime_type NOT LIKE 'multipart/%'",
            (message_id,),
        ).fetchall()
        attachments = [
            {
                "filename": r["filename"],
                "mime_type": r["mime_type"],
                "size": r["size"],
                "attachment_id": r["attachment_id"],
                "content_id": r["content_id"],
            }
            for r in attachment_rows
        ]
    except sqlite3.OperationalError as exc:
        if "no such table: attachments" in str(exc):
            attachments = []
        else:
            print(f"Database error querying attachments: {exc}", file=sys.stderr)
            attachments = []

    msg_dict["attachments"] = attachments

    # Derive body_html on-the-fly from the stored raw RFC 2822 source
    try:
        raw_source = msg_dict.get("raw") or ""
        body_html = extract_html_from_raw(raw_source)
        if body_html:
            body_html = re.sub(
                r'cid:([^\s"\'>\)]+)',
                lambda m: f'/api/cid/{m.group(1)}?msg={message_id}',
                body_html
            )
        msg_dict["body_html"] = body_html
    except Exception as exc:
        logger.error(f"Failed to extract body_html from raw for message {message_id}: {exc}")
        msg_dict["body_html"] = None

    return jsonify(msg_dict)


# ---------------------------------------------------------------------------
# GET /api/messages/<message_id>/attachments/<attachment_id>/data
# ---------------------------------------------------------------------------

def _fetch_attachment_from_gmail(message_id: str, attachment_id: str, filename: str) -> bytes:
    """Fetch attachment bytes from the Gmail API on demand.

    Gmail attachment IDs are ephemeral tokens that expire. When the stored
    attachment_id is stale we re-fetch the full message to get a fresh token,
    then match by filename to find the right attachment.
    """
    import base64
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from gmail_to_sqlite.auth import get_credentials

    db_path = current_app.config["DB_PATH"]
    data_dir = os.path.dirname(os.path.abspath(db_path))

    workspace_root = os.path.dirname(data_dir)
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)

    creds = get_credentials(data_dir)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def _download(att_id: str) -> bytes:
        result = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=att_id)
            .execute()
        )
        return base64.urlsafe_b64decode(result.get("data", ""))

    # Try the stored attachment_id first
    try:
        return _download(attachment_id)
    except HttpError as e:
        if e.resp.status != 400:
            raise
        # Token expired — re-fetch the message to get a fresh token

    raw_msg = service.users().messages().get(userId="me", id=message_id).execute()
    payload = raw_msg.get("payload", {})

    def _find_fresh_id(parts):
        for part in parts:
            # Match by filename
            part_filename = None
            for h in part.get("headers", []):
                if h["name"].lower() == "content-disposition":
                    import email.message as _em
                    m = _em.Message()
                    m["Content-Disposition"] = h["value"]
                    part_filename = m.get_param("filename", header="content-disposition")
            if part_filename is None:
                for h in part.get("headers", []):
                    if h["name"].lower() == "content-type":
                        import email.message as _em
                        m = _em.Message()
                        m["Content-Type"] = h["value"]
                        part_filename = m.get_param("name")
            fresh_id = part.get("body", {}).get("attachmentId")
            if part_filename == filename and fresh_id:
                return fresh_id
            # Recurse into nested parts
            if "parts" in part:
                found = _find_fresh_id(part["parts"])
                if found:
                    return found
        return None

    top_parts = payload.get("parts", [])
    fresh_id = _find_fresh_id(top_parts)
    if not fresh_id:
        raise ValueError(f"Could not find fresh attachment token for '{filename}' in message {message_id}")

    return _download(fresh_id)


@messages_bp.route("/messages/<message_id>/attachments/<attachment_id>/data")
def get_attachment_data(message_id: str, attachment_id: str):
    try:
        db = get_db()
        row = db.execute(
            "SELECT data, mime_type, filename FROM attachments WHERE message_id = ? AND attachment_id = ?",
            (message_id, attachment_id),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table: attachments" in str(exc):
            return jsonify({"error": "Attachment not found"}), 404
        print(f"Database error in get_attachment_data: {exc}", file=sys.stderr)
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        print(f"Database error in get_attachment_data: {exc}", file=sys.stderr)
        return jsonify({"error": str(exc)}), 500

    if row is None:
        return jsonify({"error": "Attachment not found"}), 404

    mime_type = row["mime_type"]
    filename = row["filename"] or "attachment"
    preview = request.args.get("preview") == "1"
    disposition = "inline" if preview else f'attachment; filename="{filename}"'

    def _make_response(data):
        resp = make_response(data)
        resp.headers["Content-Type"] = mime_type
        resp.headers["Content-Disposition"] = disposition
        if preview:
            resp.headers["X-Frame-Options"] = "SAMEORIGIN"
            resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    # 1. Try extracting from the stored raw RFC 2822 source (no disk I/O or API call)
    try:
        raw_row = db.execute(
            "SELECT raw FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        if raw_row and raw_row["raw"]:
            data = extract_attachment_from_raw(raw_row["raw"], filename)
            if data:
                return _make_response(data)
    except Exception as exc:
        logger.warning(f"Could not extract attachment from raw for {message_id}/{filename}: {exc}")

    # 2. Fall back to DB blob (legacy rows that stored binary data)
    if row["data"] is not None:
        return _make_response(bytes(row["data"]))

    # 3. Last resort — fetch from Gmail API on demand
    try:
        data = _fetch_attachment_from_gmail(message_id, attachment_id, filename)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"Failed to fetch attachment from Gmail: {exc}", file=sys.stderr)
        return jsonify({"error": f"Could not retrieve attachment from Gmail: {exc}"}), 502

    return _make_response(data)


# ---------------------------------------------------------------------------
# GET /api/messages/<message_id>/attachments/by-filename/<filename>/data
# Serves attachments that have no attachment_id (parsed from RFC 2822 source).
# ---------------------------------------------------------------------------

@messages_bp.route("/messages/<message_id>/attachments/by-filename/<path:filename>/data")
def get_attachment_data_by_filename(message_id: str, filename: str):
    try:
        db = get_db()
        row = db.execute(
            "SELECT data, mime_type, filename FROM attachments "
            "WHERE message_id = ? AND filename = ? AND mime_type NOT LIKE 'multipart/%' LIMIT 1",
            (message_id, filename),
        ).fetchone()
    except Exception as exc:
        print(f"Database error in get_attachment_data_by_filename: {exc}", file=sys.stderr)
        return jsonify({"error": str(exc)}), 500

    if row is None:
        return jsonify({"error": "Attachment not found"}), 404

    mime_type = row["mime_type"]
    preview = request.args.get("preview") == "1"
    disposition = "inline" if preview else f'attachment; filename="{filename}"'

    def _make_response(data):
        resp = make_response(data)
        resp.headers["Content-Type"] = mime_type
        resp.headers["Content-Disposition"] = disposition
        if preview:
            resp.headers["X-Frame-Options"] = "SAMEORIGIN"
            resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    # 1. Try extracting from the stored raw RFC 2822 source
    try:
        raw_row = db.execute(
            "SELECT raw FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        if raw_row and raw_row["raw"]:
            data = extract_attachment_from_raw(raw_row["raw"], filename)
            if data:
                return _make_response(data)
    except Exception as exc:
        logger.warning(f"Could not extract attachment from raw for {message_id}/{filename}: {exc}")

    # 2. Fall back to DB blob
    if row["data"] is not None:
        return _make_response(bytes(row["data"]))

    # 3. Last resort — fetch from Gmail API
    try:
        att_row = db.execute(
            "SELECT attachment_id FROM attachments WHERE message_id = ? AND filename = ? LIMIT 1",
            (message_id, filename),
        ).fetchone()
        att_id = att_row["attachment_id"] if att_row and att_row["attachment_id"] else ""
        data = _fetch_attachment_from_gmail(message_id, att_id, filename)
    except Exception as exc:
        print(f"Failed to fetch attachment from Gmail: {exc}", file=sys.stderr)
        return jsonify({"error": f"Could not retrieve attachment: {exc}"}), 502

    return _make_response(data)


# ---------------------------------------------------------------------------
# GET /api/cid/<content_id>?msg=<message_id>
# Serves inline images referenced as cid: in HTML bodies.
# ---------------------------------------------------------------------------

@messages_bp.route("/cid/<path:content_id>")
def get_cid_image(content_id: str):
    """Resolve a cid: inline image reference to the actual attachment data.

    The ?msg=<message_id> query param scopes the lookup to a specific message,
    which is faster and avoids cross-message collisions.
    """
    message_id = request.args.get("msg", "")

    try:
        db = get_db()
        if message_id:
            row = db.execute(
                "SELECT attachment_id, mime_type, filename FROM attachments "
                "WHERE content_id = ? AND message_id = ? LIMIT 1",
                (content_id, message_id),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT attachment_id, mime_type, filename, message_id FROM attachments "
                "WHERE content_id = ? LIMIT 1",
                (content_id,),
            ).fetchone()
    except Exception as exc:
        print(f"DB error in get_cid_image: {exc}", file=sys.stderr)
        return jsonify({"error": str(exc)}), 500

    if row is None:
        return jsonify({"error": "Inline image not found"}), 404

    attachment_id = row["attachment_id"]
    mime_type = row["mime_type"]
    filename = row["filename"] or "image"
    msg_id = message_id or row["message_id"]

    def _make_cid_response(data):
        resp = make_response(data)
        resp.headers["Content-Type"] = mime_type
        resp.headers["Content-Disposition"] = "inline"
        return resp

    # 1. Try extracting from the stored raw RFC 2822 source by Content-ID
    try:
        raw_row = db.execute(
            "SELECT raw FROM messages WHERE message_id = ?", (msg_id,)
        ).fetchone()
        if raw_row and raw_row["raw"]:
            data = extract_attachment_by_content_id(raw_row["raw"], content_id)
            if data:
                return _make_cid_response(data)
    except Exception as exc:
        logger.warning(f"Could not extract cid image from raw for {msg_id}/{content_id}: {exc}")

    # 2. Last resort — fetch from Gmail API on demand
    try:
        data = _fetch_attachment_from_gmail(msg_id, attachment_id, filename)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Could not fetch inline image: {exc}"}), 502

    return _make_cid_response(data)
