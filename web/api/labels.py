import json
import sqlite3

from flask import Blueprint, jsonify

from web.db import get_db

labels_bp = Blueprint("labels", __name__)


@labels_bp.route("/labels")
def get_labels():
    """GET /api/labels — return distinct labels from non-deleted messages, sorted alphabetically."""
    try:
        db = get_db()
        rows = db.execute(
            "SELECT labels FROM messages WHERE is_deleted = 0 AND labels IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return jsonify({
                "error": "Database not ready — please run the sync command to populate the database."
            }), 503
        return jsonify({"error": str(exc)}), 500

    label_set = set()
    for row in rows:
        try:
            labels = json.loads(row["labels"])
            if isinstance(labels, list):
                for label in labels:
                    if isinstance(label, str):
                        label_set.add(label)
        except (json.JSONDecodeError, TypeError):
            pass

    return jsonify(sorted(label_set))
