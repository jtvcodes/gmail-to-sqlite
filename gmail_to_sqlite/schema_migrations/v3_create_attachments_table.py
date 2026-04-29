"""
Migration v3: Create attachments table.

This migration creates the attachments table to store attachment metadata
and binary data extracted from multipart Gmail payloads.
"""

import logging

from ..db import database_proxy
from ..migrations import table_exists


logger = logging.getLogger(__name__)


def run() -> bool:
    """
    Create the attachments table if it doesn't already exist.

    Returns:
        bool: True if the migration was successful or table already exists,
              False if the migration failed.
    """
    table_name = "attachments"

    try:
        if table_exists(table_name):
            logger.info(f"Table {table_name} already exists")
            return True

        logger.info(f"Creating {table_name} table")

        database_proxy.obj.execute_sql(
            """
            CREATE TABLE attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL REFERENCES messages(message_id),
                filename TEXT,
                mime_type TEXT NOT NULL,
                size INTEGER NOT NULL DEFAULT 0,
                data BLOB,
                attachment_id TEXT
            )
            """
        )

        logger.info(f"Successfully created {table_name} table")
        return True

    except Exception as e:
        logger.error(f"Failed to create {table_name} table: {e}")
        return False
