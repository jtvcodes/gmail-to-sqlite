import json
import sqlite3
import sys

from flask import Blueprint, jsonify, request

from web.db import get_db

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
    "is_read",
    "is_outgoing",
    "is_deleted",
)

DETAIL_FIELDS = SUMMARY_FIELDS + ("recipients", "body")

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
            "(LOWER(subject) LIKE LOWER(?) OR LOWER(sender) LIKE LOWER(?) OR LOWER(body) LIKE LOWER(?))"
        )
        like = f"%{q}%"
        params.extend([like, like, like])

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
    order_sql = f"ORDER BY timestamp {sort_dir.upper()}"

    try:
        db = get_db()

        # total count
        count_sql = f"SELECT COUNT(*) FROM messages {where_sql}"
        total = db.execute(count_sql, params).fetchone()[0]

        # paginated results
        offset = (page - 1) * page_size
        fields_sql = ", ".join(SUMMARY_FIELDS)
        data_sql = (
            f"SELECT {fields_sql} FROM messages {where_sql} "
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

    return jsonify(
        {
            "messages": messages,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


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

    return jsonify(_row_to_dict(row, DETAIL_FIELDS))
