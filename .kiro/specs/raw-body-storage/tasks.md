# Tasks

## Task List

- [ ] 1. Add `body_html` attribute to the `Message` class
  - [~] 1.1 Add `self.body_html: Optional[str] = None` to `Message.__init__` in `gmail_to_sqlite/message.py`
  - [ ] 1.2 Add a `_extract_html_body(self, payload: Dict) -> Optional[str]` helper method that walks the payload for a `text/html` part, decodes it with `base64.urlsafe_b64decode`, and returns the string (or `None` on failure or absence)
  - [ ] 1.3 Update `_extract_body` to call `_extract_html_body` and assign the result to `self.body_html`
  - [ ] 1.4 Ensure decoding failures in `_extract_html_body` are caught and `None` is returned without propagating the exception

- [ ] 2. Add `body_html` column to the database `Message` model and `create_message` function
  - [ ] 2.1 Add `body_html = TextField(null=True)` to the `Message` model in `gmail_to_sqlite/db.py`
  - [ ] 2.2 Add `body_html=msg.body_html` to the `INSERT` fields in `create_message`
  - [ ] 2.3 Add `Message.body_html: msg.body_html` to the `ON CONFLICT` update dict in `create_message`

- [ ] 3. Implement schema migration v2 to add the `body_html` column
  - [ ] 3.1 Create `gmail_to_sqlite/schema_migrations/v2_add_body_html_column.py` following the same pattern as `v1_add_is_deleted_column.py`: check `column_exists`, use `SqliteMigrator` to add a nullable `TextField`, return `True`/`False`
  - [ ] 3.2 Update `run_migrations` in `gmail_to_sqlite/migrations.py` to run migration v2 when `current_version == 1` and advance the schema version to 2 on success

- [ ] 4. Expose `body_html` in the Web API message-detail endpoint
  - [ ] 4.1 Add `"body_html"` to the `DETAIL_FIELDS` tuple in `web/api/messages.py`
  - [ ] 4.2 Verify `"body_html"` is absent from `SUMMARY_FIELDS` (no change needed — confirm by inspection)

- [ ] 5. Write unit tests for message parsing
  - [ ] 5.1 Test non-multipart `text/html` payload: assert `body_html` equals decoded HTML and `body` is the plain-text conversion
  - [ ] 5.2 Test non-multipart `text/plain` payload: assert `body_html` is `None` and `body` is set
  - [ ] 5.3 Test multipart payload with a `text/html` part: assert `body_html` is set to the HTML part content
  - [ ] 5.4 Test multipart payload with no `text/html` part: assert `body_html` is `None`
  - [ ] 5.5 Test malformed base64 in the HTML part: assert `body_html` is `None` and no exception is raised

- [ ] 6. Write unit tests for the database layer
  - [ ] 6.1 Test that the `Message` model has a `body_html` field that is nullable
  - [ ] 6.2 Test saving a message with a non-`None` `body_html` and retrieving it
  - [ ] 6.3 Test saving a message with `body_html=None` and retrieving it

- [ ] 7. Write unit tests for migration v2
  - [ ] 7.1 Test running migration v2 on a database at version 1: assert `body_html` column exists and schema version is 2
  - [ ] 7.2 Test idempotency: run migration v2 twice and assert both calls return `True`
  - [ ] 7.3 Test that pre-existing rows have `body_html = NULL` after migration

- [ ] 8. Write unit tests for the Web API
  - [ ] 8.1 Test `GET /api/messages/<id>` returns `body_html` for a message with a non-null HTML body
  - [ ] 8.2 Test `GET /api/messages/<id>` returns `body_html: null` for a message with no HTML body
  - [ ] 8.3 Test `GET /api/messages` list response items do not contain a `body_html` key

- [ ] 9. Write property-based tests using Hypothesis
  - [ ] 9.1 Property 1 — HTML extraction round-trip: for any text string encoded as base64url in a `text/html` payload part, `Message.from_raw` produces `body_html` equal to the original string (`Feature: raw-body-storage, Property 1: HTML extraction round-trip`)
  - [ ] 9.2 Property 2 — Storage round-trip: for any `body_html` value (string or `None`), saving and retrieving a message returns the same value (`Feature: raw-body-storage, Property 2: Storage round-trip`)
  - [ ] 9.3 Property 3 — Upsert updates body_html: for any two `body_html` values, upserting with the second value results in the database containing the second value (`Feature: raw-body-storage, Property 3: Upsert updates body_html`)
  - [ ] 9.4 Property 4 — Detail API returns body_html verbatim: for any stored `body_html` value, the detail endpoint returns it unchanged (`Feature: raw-body-storage, Property 4: Detail API returns body_html verbatim`)
  - [ ] 9.5 Property 5 — List API excludes body_html: for any set of stored messages, no item in the list response contains a `body_html` key (`Feature: raw-body-storage, Property 5: List API excludes body_html`)

- [ ] 10. Add `Attachment` dataclass and `attachments` attribute to the `Message` class
  - [ ] 10.1 Define an `Attachment` dataclass in `gmail_to_sqlite/message.py` with fields: `filename: Optional[str]`, `mime_type: str`, `size: int`, `data: Optional[bytes]`, `attachment_id: Optional[str]`
  - [ ] 10.2 Add `self.attachments: List[Attachment] = []` to `Message.__init__`
  - [ ] 10.3 Add a `_extract_attachments(self, payload: Dict) -> List[Attachment]` helper method that walks multipart parts, skips `text/plain` and `text/html` parts, and extracts attachment metadata and data for all remaining parts
  - [ ] 10.4 In `_extract_attachments`, extract `filename` from the `Content-Disposition` header's `filename` parameter first, falling back to the `name` parameter in the `Content-Type` header, then `None`
  - [ ] 10.5 In `_extract_attachments`, decode `part["body"]["data"]` with `base64.urlsafe_b64decode` when present; set `data = None` when absent or when decoding fails (catch exception, continue)
  - [ ] 10.6 In `_extract_attachments`, set `attachment_id` from `part["body"]["attachmentId"]` when present, otherwise `None`
  - [ ] 10.7 Update `_extract_body` to call `self.attachments = self._extract_attachments(payload)` after the existing body extraction logic

- [ ] 11. Add `Attachment` model and `create_attachments` function to the database layer
  - [ ] 11.1 Add `from peewee import AutoField, BlobField, ForeignKeyField` imports to `gmail_to_sqlite/db.py`
  - [ ] 11.2 Define the `Attachment` model in `gmail_to_sqlite/db.py` with columns: `id` (AutoField), `message_id` (ForeignKeyField to `Message`, `column_name="message_id"`, `field="message_id"`), `filename` (TextField, null=True), `mime_type` (TextField), `size` (IntegerField, default=0), `data` (BlobField, null=True), `attachment_id` (TextField, null=True); `table_name = "attachments"`
  - [ ] 11.3 Add `Attachment` to the `db.create_tables([Message, SchemaVersion, Attachment])` call in `db.init`
  - [ ] 11.4 Implement `create_attachments(message_id: str, attachments: List) -> None` that deletes existing rows for `message_id` then bulk-inserts new rows; raises `DatabaseError` on failure
  - [ ] 11.5 Update `create_message` to call `create_attachments(msg.id, msg.attachments)` after the existing upsert

- [ ] 12. Implement schema migration v3 to create the `attachments` table
  - [ ] 12.1 Add a `table_exists(table_name: str) -> bool` helper to `gmail_to_sqlite/migrations.py` that queries `sqlite_master` to check for the table
  - [ ] 12.2 Create `gmail_to_sqlite/schema_migrations/v3_create_attachments_table.py`: check `table_exists("attachments")`; if present return `True`; otherwise execute the `CREATE TABLE attachments (...)` SQL with all required columns; return `True`/`False`
  - [ ] 12.3 Update `run_migrations` in `gmail_to_sqlite/migrations.py` to run migration v3 when `current_version == 2` and advance the schema version to 3 on success

- [ ] 13. Expose attachments in the Web API
  - [ ] 13.1 Update `get_message` in `web/api/messages.py` to query `SELECT filename, mime_type, size, attachment_id FROM attachments WHERE message_id = ?` and append an `"attachments"` key to the response dict
  - [ ] 13.2 Add a new route `GET /api/messages/<message_id>/attachments/<attachment_id>/data` in `web/api/messages.py` that queries `SELECT data, mime_type FROM attachments WHERE message_id = ? AND attachment_id = ?`
  - [ ] 13.3 In the data endpoint, return HTTP 404 with `{"error": "Attachment not found"}` when no row is found
  - [ ] 13.4 In the data endpoint, return HTTP 404 with `{"error": "Attachment data not available"}` when the row exists but `data` is `NULL`
  - [ ] 13.5 In the data endpoint, return the raw bytes with `Content-Type` set to the stored `mime_type` when data is present

- [ ] 14. Write unit tests for attachment parsing
  - [ ] 14.1 Test multipart payload with one attachment part: assert all fields (`filename`, `mime_type`, `size`, `data`, `attachment_id`) are extracted correctly
  - [ ] 14.2 Test multipart payload with multiple attachment parts: assert all attachments are present in `message.attachments`
  - [ ] 14.3 Test payload with no attachment parts (plain-text only): assert `message.attachments` is an empty list
  - [ ] 14.4 Test attachment with filename in `Content-Disposition` header: assert `filename` is extracted from that header
  - [ ] 14.5 Test attachment with filename only in `Content-Type` `name` parameter: assert fallback extraction works
  - [ ] 14.6 Test attachment with no filename in any header: assert `filename` is `None`
  - [ ] 14.7 Test attachment with malformed base64 data: assert `data` is `None` and no exception is raised
  - [ ] 14.8 Test large attachment (no `body.data`, only `body.attachmentId`): assert `data` is `None` and `attachment_id` is set

- [ ] 15. Write unit tests for the attachment database layer
  - [ ] 15.1 Test that the `Attachment` model has all required fields with correct types and nullability
  - [ ] 15.2 Test saving attachments for a message and retrieving them: assert all field values match
  - [ ] 15.3 Test that re-syncing a message replaces its attachments (call `create_attachments` twice with different data; assert only the second set is present)
  - [ ] 15.4 Test saving an attachment with `data=None` and retrieving it: assert `data` column is `NULL`

- [ ] 16. Write unit tests for migration v3
  - [ ] 16.1 Test running migration v3 on a database at version 2: assert `attachments` table exists and schema version is 3
  - [ ] 16.2 Test idempotency: run migration v3 twice and assert both calls return `True`

- [ ] 17. Write unit tests for the attachment Web API
  - [ ] 17.1 Test `GET /api/messages/<id>` returns an `attachments` array with correct shape (fields present, no `data` key) for a message with attachments
  - [ ] 17.2 Test `GET /api/messages/<id>` returns an empty `attachments` array for a message with no attachments
  - [ ] 17.3 Test `GET /api/messages/<id>/attachments/<aid>/data` returns raw bytes with correct `Content-Type` for an attachment with non-null data
  - [ ] 17.4 Test `GET /api/messages/<id>/attachments/<aid>/data` returns HTTP 404 when the attachment does not exist
  - [ ] 17.5 Test `GET /api/messages/<id>/attachments/<aid>/data` returns HTTP 404 when the attachment's `data` is `NULL`

- [ ] 18. Write property-based tests for attachment storage using Hypothesis
  - [ ] 18.1 Property 6 — Attachment extraction completeness: for any multipart payload with one or more attachment parts, `Message.from_raw` produces an `attachments` list with one entry per part, each having the correct `filename`, `mime_type`, `size`, and `attachment_id` (`Feature: raw-body-storage, Property 6: Attachment extraction completeness`)
  - [ ] 18.2 Property 7 — Attachment storage round-trip: for any list of attachments saved via `create_attachments`, querying the DB returns rows with matching field values (`Feature: raw-body-storage, Property 7: Attachment storage round-trip`)
  - [ ] 18.3 Property 8 — Detail API attachments array shape: for any message stored with attachments, every item in the `attachments` array of the detail response has keys `filename`, `mime_type`, `size`, `attachment_id` and does NOT have key `data` (`Feature: raw-body-storage, Property 8: Detail API attachments array shape`)
  - [ ] 18.4 Property 9 — Attachment data endpoint round-trip: for any attachment stored with non-null data, the data endpoint returns the exact bytes that were stored (`Feature: raw-body-storage, Property 9: Attachment data endpoint round-trip`)
