import json
import sqlite3

from flask import Blueprint, jsonify

from web.db import get_db

labels_bp = Blueprint("labels", __name__)

_QUERY = """
WITH label_types AS (
    SELECT 'INBOX'               AS label, 'system'   AS label_type UNION ALL
    SELECT 'STARRED',                      'system'                 UNION ALL
    SELECT 'SNOOZED',                      'system'                 UNION ALL
    SELECT 'IMPORTANT',                    'system'                 UNION ALL
    SELECT 'SENT',                         'system'                 UNION ALL
    SELECT 'SCHEDULED',                    'system'                 UNION ALL
    SELECT 'DRAFTS',                       'system'                 UNION ALL
    SELECT 'ALL_MAIL',                     'system'                 UNION ALL
    SELECT 'SPAM',                         'system'                 UNION ALL
    SELECT 'TRASH',                        'system'                 UNION ALL
    SELECT 'CHAT',                         'system'                 UNION ALL
    SELECT 'CATEGORY_PURCHASES',           'category'               UNION ALL
    SELECT 'CATEGORY_SOCIAL',              'category'               UNION ALL
    SELECT 'CATEGORY_UPDATES',             'category'               UNION ALL
    SELECT 'CATEGORY_FORUMS',              'category'               UNION ALL
    SELECT 'CATEGORY_PROMOTIONS',          'category'
)
SELECT DISTINCT
    value                                        AS label,
    COALESCE(lt.label_type, 'label')             AS label_type
FROM messages, json_each(messages.labels)
LEFT JOIN label_types lt ON lt.label = value
WHERE value != 'UNREAD'
  AND value != 'YELLOW_STAR'
  AND value != 'CATEGORY_PERSONAL'
ORDER BY label
"""


@labels_bp.route("/labels")
def get_labels():
    """Return distinct labels with their type: system | category | label."""
    try:
        db = get_db()
        rows = db.execute(_QUERY).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return jsonify({
                "error": "Database not ready — please run the sync command to populate the database."
            }), 503
        return jsonify({"error": str(exc)}), 500

    return jsonify([
        {"label": row["label"], "label_type": row["label_type"]}
        for row in rows
    ])
