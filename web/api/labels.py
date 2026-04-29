import json

from flask import Blueprint, jsonify

from web.db import get_db

labels_bp = Blueprint("labels", __name__)


@labels_bp.route("/labels")
def get_labels():
    """GET /api/labels — return distinct labels from non-deleted messages, sorted alphabetically."""
    db = get_db()
    rows = db.execute(
        "SELECT labels FROM messages WHERE is_deleted = 0 AND labels IS NOT NULL"
    ).fetchall()

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
