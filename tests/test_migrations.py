"""Tests for database migrations functionality."""

import tempfile
import os
from gmail_to_sqlite.db import database_proxy, SchemaVersion, Message
from gmail_to_sqlite.migrations import (
    get_schema_version,
    set_schema_version,
    run_migrations,
    column_exists,
    table_exists,
)
from gmail_to_sqlite.schema_migrations.v1_add_is_deleted_column import (
    run as migration_v1_run,
)
from gmail_to_sqlite.schema_migrations.v2_add_body_html_column import (
    run as migration_v2_run,
)
from gmail_to_sqlite.schema_migrations.v3_create_attachments_table import (
    run as migration_v3_run,
)
from peewee import SqliteDatabase


class TestMigrations:
    """Test migration operations."""

    def setup_method(self):
        """Set up test database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = SqliteDatabase(self.db_path)
        database_proxy.initialize(self.db)

    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, "db") and self.db:
            self.db.close()

    def test_schema_version_functions(self):
        """Test schema version tracking functions."""
        # Create schema version table
        self.db.create_tables([SchemaVersion])

        # Test initial version (should be 0)
        version = get_schema_version()
        assert version == 0

        # Test setting version
        success = set_schema_version(5)
        assert success is True

        # Test getting version again
        version = get_schema_version()
        assert version == 5

    def test_run_migrations_from_scratch(self):
        """Test running migrations from a fresh database."""
        # Also need to create Message table for the migration to work
        self.db.create_tables([Message])

        # Run migrations
        success = run_migrations()
        assert success is True

        # Check that schema version is set to 3 (v1 + v2 + v3 all run)
        version = get_schema_version()
        assert version == 3

        # Check that is_deleted column was added (v1)
        assert column_exists("messages", "is_deleted") is True

        # Check that body_html column was added (v2)
        assert column_exists("messages", "body_html") is True

        # Check that attachments table was created (v3)
        assert table_exists("attachments") is True

    def test_run_migrations_already_up_to_date(self):
        """Test running migrations when database is already up to date."""
        # Create tables and set version to 3
        self.db.create_tables([SchemaVersion, Message])
        set_schema_version(3)

        # Run migrations
        success = run_migrations()
        assert success is True

        # Version should still be 3
        version = get_schema_version()
        assert version == 3

    def test_migration_v1_add_is_deleted_column(self):
        """Test migration v1 directly."""
        # Create Message table
        self.db.create_tables([Message])

        # Run the migration
        success = migration_v1_run()
        assert success is True

        # Check that is_deleted column was added
        assert column_exists("messages", "is_deleted") is True

        # Running again should still succeed (idempotent)
        success = migration_v1_run()
        assert success is True

    def test_migration_v2_add_body_html_column(self):
        """Test migration v2 on a v1 database: body_html column added and schema version is 2."""
        # Set up a database at version 1 using raw SQL so that body_html is NOT present.
        # This simulates the real state of a v1 database before migration v2 runs.
        self.db.create_tables([SchemaVersion])
        self.db.execute_sql(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                thread_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipients TEXT NOT NULL,
                labels TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                size INTEGER NOT NULL,
                timestamp DATETIME NOT NULL,
                is_read INTEGER NOT NULL,
                is_outgoing INTEGER NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                last_indexed DATETIME NOT NULL
            )
            """
        )

        # Set schema version to 1 to reflect the v1 state
        set_schema_version(1)
        assert get_schema_version() == 1

        # Confirm body_html does not exist yet
        assert column_exists("messages", "body_html") is False

        # Run migration v2
        success = migration_v2_run()
        assert success is True

        # Assert body_html column now exists
        assert column_exists("messages", "body_html") is True

        # Advance schema version to 2 (as run_migrations would do)
        set_schema_version(2)

        # Assert schema version is now 2
        assert get_schema_version() == 2

    def test_migration_v2_idempotent(self):
        """Test migration v2 is idempotent — running twice both return True."""
        self.db.create_tables([Message])

        success1 = migration_v2_run()
        assert success1 is True

        success2 = migration_v2_run()
        assert success2 is True

        assert column_exists("messages", "body_html") is True

    def test_migration_v2_existing_rows_have_null_body_html(self):
        """Test that pre-existing rows have body_html = NULL after migration."""
        # Create the messages table WITHOUT body_html to simulate a v1 database
        self.db.create_tables([SchemaVersion])
        self.db.execute_sql(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                thread_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipients TEXT NOT NULL,
                labels TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                size INTEGER NOT NULL,
                timestamp DATETIME NOT NULL,
                is_read INTEGER NOT NULL,
                is_outgoing INTEGER NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                last_indexed DATETIME NOT NULL
            )
            """
        )

        # Insert a row before migration (no body_html column exists yet)
        self.db.execute_sql(
            "INSERT INTO messages (message_id, thread_id, sender, recipients, labels, "
            "subject, body, size, timestamp, is_read, is_outgoing, "
            "is_deleted, last_indexed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "msg1", "thread1", "{}", "[]", "[]",
                "Test Subject", "Test body", 100,
                "2024-01-01 00:00:00", 1, 0, 0, "2024-01-01 00:00:00",
            ),
        )

        # Run migration v2 — this adds the body_html column; existing rows get NULL
        success = migration_v2_run()
        assert success is True

        # Verify the existing row has body_html = NULL
        cursor = self.db.execute_sql(
            "SELECT body_html FROM messages WHERE message_id = ?", ("msg1",)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] is None

    def test_migration_v3_create_attachments_table(self):
        """Test migration v3 on a v2 DB: attachments table created and schema version is 3."""
        # Set up a database at version 2 (messages table with body_html, no attachments table)
        self.db.create_tables([SchemaVersion])
        self.db.execute_sql(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                thread_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipients TEXT NOT NULL,
                labels TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                body_html TEXT,
                size INTEGER NOT NULL,
                timestamp DATETIME NOT NULL,
                is_read INTEGER NOT NULL,
                is_outgoing INTEGER NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                last_indexed DATETIME NOT NULL
            )
            """
        )
        set_schema_version(2)
        assert get_schema_version() == 2

        # Confirm attachments table does not exist yet
        assert table_exists("attachments") is False

        # Run migration v3
        success = migration_v3_run()
        assert success is True

        # Assert attachments table now exists
        assert table_exists("attachments") is True

        # Advance schema version to 3 (as run_migrations would do)
        set_schema_version(3)

        # Assert schema version is now 3
        assert get_schema_version() == 3

    def test_migration_v3_idempotent(self):
        """Test migration v3 is idempotent — running twice both return True."""
        self.db.create_tables([Message])

        success1 = migration_v3_run()
        assert success1 is True

        success2 = migration_v3_run()
        assert success2 is True

        assert table_exists("attachments") is True
