"""
Migration v4: Add content_id column to attachments table.

Stores the Content-ID header value for inline images so cid: references
in HTML bodies can be resolved to the actual attachment.
"""

import logging

from ..db import database_proxy
from ..migrations import column_exists

logger = logging.getLogger(__name__)


def run() -> bool:
    try:
        if column_exists("attachments", "content_id"):
            logger.info("Column content_id already exists in attachments table")
            return True

        logger.info("Adding content_id column to attachments table")
        database_proxy.obj.execute_sql(
            "ALTER TABLE attachments ADD COLUMN content_id TEXT"
        )
        logger.info("Successfully added content_id column")
        return True
    except Exception as e:
        logger.error(f"Failed to add content_id column: {e}")
        return False
