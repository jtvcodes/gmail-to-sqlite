"""
Migration v2: Add body_html column to messages table.

This migration adds a nullable TextField to store the raw HTML body
of each Gmail message.
"""

import logging
from peewee import TextField
from playhouse.migrate import SqliteMigrator, migrate

from ..db import database_proxy
from ..migrations import column_exists


logger = logging.getLogger(__name__)


def run() -> bool:
    """
    Add the body_html column to the messages table if it doesn't exist.

    This migration adds a nullable TextField to store the raw HTML body
    of each Gmail message. Existing rows will have body_html = NULL.

    Returns:
        bool: True if the migration was successful or column already exists,
              False if the migration failed.
    """
    table_name = "messages"
    column_name = "body_html"

    try:
        if column_exists(table_name, column_name):
            logger.info(f"Column {column_name} already exists in {table_name} table")
            return True

        logger.info(f"Adding {column_name} column to {table_name} table")

        migrator = SqliteMigrator(database_proxy.obj)
        body_html_field = TextField(null=True)

        migrate(migrator.add_column(table_name, column_name, body_html_field))

        logger.info(f"Successfully added {column_name} column to {table_name} table")
        return True

    except Exception as e:
        logger.error(f"Failed to add {column_name} column: {e}")
        return False
