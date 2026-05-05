import email as _email_mod
import json
import logging
import re
import sqlite3
import threading
from functools import lru_cache
from typing import List, Optional

import flask
from flask import Blueprint, jsonify, request

from gmail_to_sqlite.message import (
    _decode_header,
    extract_html_from_raw,
    extract_attachment_from_raw,
    extract_attachment_by_content_id,
)
from web.db import get_db

logger = logging.getLogger(__name__)

messages_bp = Blueprint("messages", __name__)

# ---------------------------------------------------------------------------
# In-process attachment metadata cache
# Keyed by message_id → list of Attachment-like dicts (no binary data).
# Thread-safe via a simple lock; bounded to 256 entries.
# ---------------------------------------------------------------------------

_att_cache: dict = {}
_att_cache_lock = threading.Lock()
_ATT_CACHE_MAX = 256


def _cache_get(message_id: str) -> Optional[List[dict]]:
    with _att_cache_lock:
        return _att_cache.get(message_id)


def _cache_set(message_id: str, attachments: List[dict]) -> None:
    with _att_cache_lock:
        if len(_att_cache) >= _ATT_CACHE_MAX:
            # Evict the oldest entry (insertion-order dict, Python 3.7+)
            oldest = next(iter(_att_cache))
            del _att_cache[oldest]
        _att_cache[message_id] = attachments


def _parse_attachments_from_raw(raw: Optional[str]) -> List[dict]:
    """Parse attachment metadata from a stored RFC 2822 string.

    Returns a list of dicts with keys: filename, mime_type, size,
    attachment_id (always None — not available from raw), content_id.
    Binary data is NOT loaded; callers use extract_attachment_from_raw /
    extract_attachment_by_content_id when they need the bytes.
    """
    if not raw:
        return []
    try:
        parsed = _email_mod.message_from_string(raw)
        if not parsed.is_multipart():
            return []
        results = []
        for part in parsed.walk():
            mime_type = part.get_content_type()
            if mime_type in ("text/plain", "text/html") or mime_type.startswith("multipart/"):
                continue

            filename: Optional[str] = part.get_filename()
            if not filename:
                filename = part.get_param("name")
            if filename:
                filename = _decode_header(filename)

            content_id: Optional[str] = None
            raw_cid = part.get("Content-ID", "")
            if raw_cid:
                content_id = raw_cid.strip("<>")

            if not filename and not content_id:
                continue

            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0

            results.append({
                "filename": filename,
                "mime_type": mime_type,
                "size": size,
                "attachment_id": None,   # not available from RFC 2822
                "content_id": content_id,
            })
        return results
    except Exception as exc:
        logger.debug(f"Failed to parse attachments from raw: {exc}")
        return []


def _get_attachments(message_id: str, raw: Optional[str]) -> List[dict]:
    """Return attachment metadata for a message, using the cache."""
    cached = _cache_get(message_id)
    if cached is not None:
        return cached
    attachments = _parse_attachments_from_raw(raw)
    _cache_set(message_id, attachments)
    return attachments


# ---------------------------------------------------------------------------
# Column sets
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

DETAIL_FIELDS = SUMMARY_FIELDS + ("recipients", "body", "raw")

BOOL_FIELDS = {"is_read", "is_outgoing", "is_deleted"}

JSON_FIELDS = {"sender", "recipients", "labels"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row, fields: tuple) -> dict:
    d = {}
    for field in fields:
        val = row[field]
        if field in JSON_FIELDS and isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        elif field in BOOL_FIELDS and val is not None:
            val = bool(val)
        d[field] = val
    return d


def _parse_bool_param(value: str, name: str) -> bool:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise ValueError(f"'{name}' must be 'true' or 'false'")


def _missing_table(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "no such table" in str(exc)


# ---------------------------------------------------------------------------
# GET /api/messages
# ---------------------------------------------------------------------------

@messages_bp.route("/messages")
def list_messages() -> flask.Response:
    # --- pagination ---
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

    # --- filters ---
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
            include_deleted = _parse_bool_param(request.args["include_deleted"], "include_deleted")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    # --- build WHERE ---
    conditions = []
    params: list = []

    if not include_deleted:
        conditions.append("is_deleted = 0")

    if q:
        conditions.append(
            "(LOWER(subject) LIKE LOWER(?) OR LOWER(sender) LIKE LOWER(?)"
            " OR LOWER(body) LIKE LOWER(?) OR message_id = ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like, q])

    if label:
        conditions.append(
            "EXISTS (SELECT 1 FROM json_each(labels) WHERE json_each.value = ?)"
        )
        params.append(label)

    if is_read is not None:
        conditions.append("is_read = ?")
        params.append(1 if is_read else 0)

    if is_outgoing is not None:
        conditions.append("is_outgoing = ?")
        params.append(1 if is_outgoing else 0)

    where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # --- sort ---
    sort_dir = request.args.get("sort_dir", "desc").lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"
    order_sql = f"ORDER BY timestamp {sort_dir.upper()}"

    db = get_db()
    try:
        total = db.execute(f"SELECT COUNT(*) FROM messages {where_sql}", params).fetchone()[0]

        offset = (page - 1) * page_size
        fields_sql = ", ".join(SUMMARY_FIELDS) + ", raw"
        rows = db.execute(
            f"SELECT {fields_sql} FROM messages {where_sql} {order_sql} LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
    except sqlite3.Error as exc:
        if _missing_table(exc):
            return jsonify({
                "error": "Database not ready — please run a sync to populate the database."
            }), 503
        return jsonify({"error": str(exc)}), 500

    messages = []
    for row in rows:
        msg = _row_to_dict(row, SUMMARY_FIELDS)
        raw = row["raw"]
        atts = _get_attachments(row["message_id"], raw)
        msg["attachment_count"] = len(atts)
        messages.append(msg)

    return jsonify({"messages": messages, "total": total, "page": page, "page_size": page_size})


# ---------------------------------------------------------------------------
# GET /api/messages/stats
# ---------------------------------------------------------------------------

@messages_bp.route("/messages/stats")
def messages_stats() -> flask.Response:
    try:
        db = get_db()
        total_messages = db.execute(
            "SELECT COUNT(*) FROM messages WHERE is_deleted = 0"
        ).fetchone()[0]
        try:
            total_indexed = db.execute("SELECT COUNT(*) FROM gmail_index").fetchone()[0]
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
    except sqlite3.Error as exc:
        if _missing_table(exc):
            return jsonify({"total_messages": 0, "total_indexed": 0, "total_unsynced": 0})
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /api/messages/<message_id>
# ---------------------------------------------------------------------------

@messages_bp.route("/messages/<message_id>")
def get_message(message_id: str) -> flask.Response:
    try:
        db = get_db()
        fields_sql = ", ".join(DETAIL_FIELDS)
        row = db.execute(
            f"SELECT {fields_sql} FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        if _missing_table(exc):
            return jsonify({"error": "Database not ready — please run a sync."}), 503
        return jsonify({"error": str(exc)}), 500

    if row is None:
        return jsonify({"error": "Message not found"}), 404

    msg = _row_to_dict(row, DETAIL_FIELDS)
    raw = msg.get("raw")

    # Attachments — derived on-the-fly from raw, cached in-process
    msg["attachments"] = _get_attachments(message_id, raw)

    # Derive body_html from stored raw RFC 2822 source
    try:
        body_html = extract_html_from_raw(raw or "")
        if body_html:
            body_html = re.sub(
                r'cid:([^\s"\'>\)]+)',
                lambda m: f'/api/cid/{m.group(1)}?msg={message_id}',
                body_html
            )
        msg["body_html"] = body_html
    except Exception as exc:
        logger.error(f"Failed to extract body_html for message {message_id}: {exc}")
        msg["body_html"] = None

    return jsonify(msg)


# ---------------------------------------------------------------------------
# GET /api/messages/<message_id>/attachments/by-filename/<filename>/data
# ---------------------------------------------------------------------------

@messages_bp.route("/messages/<message_id>/attachments/by-filename/<path:filename>/data")
def get_attachment_data_by_filename(message_id: str, filename: str) -> flask.Response:
    db = get_db()
    try:
        row = db.execute(
            "SELECT raw FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 500

    if row is None:
        return jsonify({"error": "Message not found"}), 404

    raw = row["raw"]

    # Check the attachment exists in the metadata
    atts = _get_attachments(message_id, raw)
    att_meta = next((a for a in atts if a["filename"] == filename), None)
    if att_meta is None:
        return jsonify({"error": "Attachment not found"}), 404

    data = extract_attachment_from_raw(raw, filename)
    if data is None:
        return jsonify({"error": "Attachment data not available"}), 404

    from flask import make_response
    preview = request.args.get("preview") == "1"
    disposition = "inline" if preview else f'attachment; filename="{filename}"'
    resp = make_response(data)
    resp.headers["Content-Type"] = att_meta["mime_type"]
    resp.headers["Content-Disposition"] = disposition
    return resp


# ---------------------------------------------------------------------------
# GET /api/cid/<content_id>?msg=<message_id>
# ---------------------------------------------------------------------------

@messages_bp.route("/cid/<path:content_id>")
def get_cid_image(content_id: str) -> flask.Response:
    message_id = request.args.get("msg", "")
    if not message_id:
        return jsonify({"error": "msg parameter required"}), 400

    db = get_db()
    try:
        row = db.execute(
            "SELECT raw FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 500

    if row is None:
        return jsonify({"error": "Message not found"}), 404

    raw = row["raw"]

    # Verify the content_id exists in this message's attachments
    atts = _get_attachments(message_id, raw)
    att_meta = next((a for a in atts if a.get("content_id") == content_id), None)
    if att_meta is None:
        return jsonify({"error": "Inline image not found"}), 404

    data = extract_attachment_by_content_id(raw, content_id)
    if data is None:
        return jsonify({"error": "Inline image data not available"}), 404

    from flask import make_response
    resp = make_response(data)
    resp.headers["Content-Type"] = att_meta["mime_type"]
    resp.headers["Content-Disposition"] = "inline"
    return resp
