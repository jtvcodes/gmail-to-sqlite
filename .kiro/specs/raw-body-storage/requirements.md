# Requirements Document

## Introduction

This feature extends the gmail-to-sqlite project in two related ways:

1. **HTML body storage** — preserve the raw HTML body of each Gmail message in a new `body_html` field so that consumers (such as the web viewer) can render rich email content rather than plain text.
2. **Attachment storage** — extract attachment metadata and binary data from multipart Gmail payloads and persist them in a new `attachments` table, with a web API endpoint to retrieve attachment data.

The change touches four layers of the system:
1. **Message parsing** — extract and retain the raw HTML alongside the plain-text conversion, and extract attachment metadata and data from multipart payloads.
2. **Database schema** — add a nullable `body_html` column to the `messages` table and a new `attachments` table.
3. **Schema migration** — add migrations that safely add the column and create the table in existing databases.
4. **Web API** — expose `body_html` in the message-detail endpoint and add an `attachments` array; provide a separate endpoint to serve raw attachment data.

## Glossary

- **Message_Parser**: The component in `gmail_to_sqlite/message.py` responsible for converting raw Gmail API payloads into `Message` objects.
- **Database**: The SQLite database managed by `gmail_to_sqlite/db.py` that stores synced messages.
- **Migration_Runner**: The component in `gmail_to_sqlite/migrations.py` that applies schema migrations on startup.
- **Web_API**: The Flask application in `web/` that serves message data to the web viewer.
- **body**: The existing plain-text representation of a message body stored in the `messages` table.
- **body_html**: The field that stores the raw HTML content of a message body.
- **MIME type**: The content type identifier (e.g., `text/html`, `text/plain`, `application/pdf`) used to identify message parts in a Gmail API payload.
- **Multipart message**: A Gmail message whose payload contains multiple parts, each with its own MIME type.
- **Attachment**: A non-body part of a multipart Gmail message (i.e., not `text/plain` or `text/html`), representing a file attached to the email.
- **attachment_id**: The Gmail API identifier for a large attachment that must be fetched separately via the Gmail API.

---

## Requirements

### Requirement 1: Extract Raw HTML During Message Parsing

**User Story:** As a developer syncing Gmail messages, I want the raw HTML body to be extracted and stored alongside the plain-text body, so that downstream consumers have access to the original formatted content.

#### Acceptance Criteria

1. WHEN a Gmail API payload contains a part with MIME type `text/html`, THE Message_Parser SHALL decode that part and store the result in the `body_html` attribute of the `Message` object.
2. WHEN a Gmail API payload contains no part with MIME type `text/html`, THE Message_Parser SHALL set `body_html` to `None`.
3. WHEN a Gmail API payload is a non-multipart message with MIME type `text/html`, THE Message_Parser SHALL store the decoded content in `body_html` and also convert it to plain text for `body`.
4. WHEN a Gmail API payload is a non-multipart message with MIME type `text/plain`, THE Message_Parser SHALL set `body_html` to `None` and store the decoded content in `body`.
5. WHEN decoding of the HTML part fails, THE Message_Parser SHALL set `body_html` to `None` and SHALL continue parsing the remainder of the message without raising an exception.
6. THE Message_Parser SHALL preserve the existing `body` plain-text extraction behaviour unchanged.

---

### Requirement 2: Database Schema — body_html Column

**User Story:** As a developer, I want the `messages` table to include a `body_html` column, so that raw HTML bodies can be persisted alongside plain-text bodies.

#### Acceptance Criteria

1. THE Database SHALL define a nullable `TextField` column named `body_html` on the `Message` model.
2. WHEN a `Message` object with a non-`None` `body_html` is saved, THE Database SHALL persist the HTML string in the `body_html` column.
3. WHEN a `Message` object with `body_html` equal to `None` is saved, THE Database SHALL store `NULL` in the `body_html` column.
4. WHEN a message is updated via the upsert conflict resolution path, THE Database SHALL update the `body_html` column to reflect the latest value.

---

### Requirement 3: Schema Migration for Existing Databases — body_html

**User Story:** As a user with an existing messages database, I want the migration to add the `body_html` column automatically on startup, so that I do not need to manually alter my database.

#### Acceptance Criteria

1. WHEN the Migration_Runner runs against a database at schema version 1, THE Migration_Runner SHALL apply migration v2 which adds the `body_html` column to the `messages` table.
2. WHEN the `body_html` column already exists in the `messages` table, THE Migration_Runner SHALL skip the column-addition step and return success without error.
3. WHEN the `body_html` column is successfully added, THE Migration_Runner SHALL set the schema version to 2.
4. IF the column-addition SQL statement fails, THEN THE Migration_Runner SHALL log the error and return `False` without advancing the schema version.
5. WHEN migration v2 runs, THE Migration_Runner SHALL set all existing rows' `body_html` column to `NULL`.

---

### Requirement 4: Web API Exposes body_html in Message Detail

**User Story:** As a web viewer user, I want the message-detail API response to include the raw HTML body, so that the viewer can render rich email content.

#### Acceptance Criteria

1. WHEN a client requests `GET /api/messages/<message_id>`, THE Web_API SHALL include `body_html` in the JSON response object.
2. WHEN the stored `body_html` value is `NULL`, THE Web_API SHALL return `null` for the `body_html` field in the JSON response.
3. WHEN the stored `body_html` value is a non-empty string, THE Web_API SHALL return that string verbatim as the `body_html` field value.
4. THE Web_API SHALL NOT include `body_html` in the list-messages (`GET /api/messages`) summary response, so that large HTML payloads do not inflate list responses.

---

### Requirement 5: Round-Trip Integrity of HTML Extraction

**User Story:** As a developer, I want confidence that the HTML extraction and storage pipeline is correct, so that the stored HTML faithfully represents what was in the original Gmail payload.

#### Acceptance Criteria

1. FOR ALL Gmail API payloads that contain a `text/html` part with valid base64url-encoded data, THE Message_Parser SHALL produce a `body_html` value such that re-encoding it with base64url and decoding it again yields the original string (round-trip property).
2. WHEN `body_html` is stored and then retrieved from the Database, THE Database SHALL return a string equal to the one that was stored (storage round-trip property).

---

### Requirement 6: Extract Attachments During Message Parsing

**User Story:** As a developer syncing Gmail messages, I want attachment metadata and data to be extracted from multipart payloads, so that attachments can be stored and later retrieved.

#### Acceptance Criteria

1. WHEN a Gmail API payload contains multipart parts that are not `text/plain` or `text/html`, THE Message_Parser SHALL extract each such part as an `Attachment` with `filename`, `mime_type`, `size`, `data`, and `attachment_id` fields.
2. WHEN a Gmail API payload contains no attachment parts, THE Message_Parser SHALL set the `attachments` attribute to an empty list.
3. WHEN an attachment part has a `Content-Disposition` header with a `filename` parameter, THE Message_Parser SHALL use that value as the attachment's `filename`.
4. WHEN an attachment part has no `Content-Disposition` filename but has a `name` parameter in its `Content-Type` header, THE Message_Parser SHALL use that value as the attachment's `filename`.
5. WHEN an attachment part has no filename in any header, THE Message_Parser SHALL set `filename` to `None`.
6. WHEN an attachment part has a `body.data` field, THE Message_Parser SHALL decode it with `base64.urlsafe_b64decode` and store the result as `data` (bytes).
7. WHEN an attachment part has no `body.data` field (large attachment), THE Message_Parser SHALL set `data` to `None` and store the `body.attachmentId` value as `attachment_id`.
8. WHEN decoding of an attachment part's data fails, THE Message_Parser SHALL set `data` to `None` for that attachment and SHALL continue parsing remaining parts without raising an exception.

---

### Requirement 7: Database Schema — attachments Table

**User Story:** As a developer, I want a dedicated `attachments` table in the database, so that attachment metadata and data can be persisted and queried independently of messages.

#### Acceptance Criteria

1. THE Database SHALL define an `Attachment` model with columns: `id` (auto integer PK), `message_id` (FK to `messages.message_id`), `filename` (nullable text), `mime_type` (text), `size` (integer, default 0), `data` (BLOB, nullable), `attachment_id` (nullable text).
2. WHEN attachments are saved for a message, THE Database SHALL persist all attachment rows linked to that `message_id`.
3. WHEN a message is re-synced, THE Database SHALL replace all existing attachment rows for that `message_id` with the newly extracted attachments (idempotent upsert).
4. WHEN an attachment has `data = None` (large attachment not yet fetched), THE Database SHALL store `NULL` in the `data` column.

---

### Requirement 8: Schema Migration — attachments Table

**User Story:** As a user with an existing messages database, I want the migration to create the `attachments` table automatically on startup, so that I do not need to manually alter my database.

#### Acceptance Criteria

1. WHEN the Migration_Runner runs against a database at schema version 2, THE Migration_Runner SHALL apply migration v3 which creates the `attachments` table.
2. WHEN the `attachments` table already exists, THE Migration_Runner SHALL skip table creation and return success without error.
3. WHEN the `attachments` table is successfully created, THE Migration_Runner SHALL set the schema version to 3.
4. IF the table-creation SQL statement fails, THEN THE Migration_Runner SHALL log the error and return `False` without advancing the schema version.

---

### Requirement 9: Web API Exposes Attachments

**User Story:** As a web viewer user, I want the message-detail API response to include attachment metadata, and I want to be able to retrieve raw attachment data via a dedicated endpoint, so that I can display and download email attachments.

#### Acceptance Criteria

1. WHEN a client requests `GET /api/messages/<message_id>`, THE Web_API SHALL include an `attachments` array in the JSON response, where each item represents one attachment for that message.
2. WHEN an attachment item is included in the `attachments` array, it SHALL contain the fields `filename`, `mime_type`, `size`, and `attachment_id`, and SHALL NOT contain the `data` field.
3. WHEN a message has no attachments, THE Web_API SHALL return an empty `attachments` array in the detail response.
4. WHEN a client requests `GET /api/messages/<message_id>/attachments/<attachment_id>/data` and the attachment exists with non-null data, THE Web_API SHALL return the raw attachment bytes with the stored `mime_type` as the `Content-Type` header.
5. WHEN a client requests `GET /api/messages/<message_id>/attachments/<attachment_id>/data` and the attachment does not exist, THE Web_API SHALL return HTTP 404.
6. WHEN a client requests `GET /api/messages/<message_id>/attachments/<attachment_id>/data` and the attachment's `data` is `NULL`, THE Web_API SHALL return HTTP 404 with an appropriate error message.
