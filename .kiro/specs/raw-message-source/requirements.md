# Requirements Document

## Introduction

This feature replaces the stored `body_html` column in the `messages` table with a `raw` column that holds the complete RFC 2822 email source (all transport headers + full MIME body, decoded from the base64url-encoded `format=raw` Gmail API response). The HTML body shown in the UI is derived on-the-fly from the stored raw source at API response time. A "View source" link is added to the message detail panel so users can inspect the full raw email in a scrollable monospace modal.

A `received_date` column is also added to the `messages` table. It stores the timestamp parsed from the topmost `Received:` header in the raw source — the date the receiving mail server accepted the message — which is more reliable than the sender-supplied `Date:` header. The UI uses `received_date` (falling back to `timestamp` when absent) as the displayed message date throughout the message list and detail panel.

## Glossary

- **Raw_Source**: The complete RFC 2822 email string, including all transport headers (`Delivered-To`, `Received`, `DKIM-Signature`, `Return-Path`, etc.) and the full MIME body, decoded from the base64url payload returned by the Gmail API `format=raw` request.
- **Gmail_API**: The Google Gmail REST API v1 used to fetch and list messages.
- **Sync_Engine**: The Python module `gmail_to_sqlite/sync.py` responsible for fetching messages from the Gmail API and persisting them to the database.
- **Message_Parser**: The Python class `gmail_to_sqlite/message.py::Message` responsible for parsing a Gmail API response into a structured `Message` object.
- **DB_Layer**: The Python module `gmail_to_sqlite/db.py` that defines the Peewee ORM models and database helper functions.
- **Migration_Runner**: The Python module `gmail_to_sqlite/migrations.py` that applies sequential schema migrations.
- **API_Server**: The Flask blueprint `web/api/messages.py` that serves the `/api/messages` endpoints.
- **Detail_Panel**: The JavaScript component `web/static/messageDetail.js` that renders the message detail side panel in the browser.
- **Source_Modal**: A full-screen browser modal that displays the Raw_Source in a monospace, scrollable, selectable `<pre>` block.
- **HTML_Extractor**: The server-side function within the API_Server that derives the displayable HTML body from a stored Raw_Source string.
- **CID_Rewriter**: The existing logic in the API_Server that rewrites `cid:` inline image references to `/api/cid/<content_id>?msg=<message_id>` URLs.
- **Received_Date**: The datetime parsed from the date portion of the **last** `Received:` header in the Raw_Source (the final delivery hop, i.e. the server that placed the message in the recipient's mailbox). Falls back to the last `X-Received:` header if no `Received:` date is parseable. Represents when the message was actually delivered, as opposed to `timestamp` (Gmail's internal ingest time) or the `Date:` header (sender-supplied, potentially unreliable).
- **Display_Date**: The date shown to the user in the message list and detail panel. Equals `received_date` when non-null; falls back to `timestamp` otherwise.

---

## Requirements

### Requirement 1: Database Schema Migration

**User Story:** As a developer, I want the `messages` table to store the complete raw RFC 2822 source instead of the extracted HTML body, and to store the server-side received date separately from the existing timestamp, so that no information is lost during sync and the full email can be inspected later.

#### Acceptance Criteria

1. THE DB_Layer SHALL define a `raw` column of type `TEXT` (nullable) on the `messages` table in place of the `body_html` column.
2. THE DB_Layer SHALL define a `received_date` column of type `DATETIME` (nullable) on the `messages` table.
3. THE Migration_Runner SHALL apply a v5 migration that renames the `body_html` column to `raw` and adds the `received_date` column to the `messages` table.
4. WHEN the v5 migration runs on a database that already has a `body_html` column, THE Migration_Runner SHALL rename that column to `raw` and preserve all existing row data.
5. WHEN the v5 migration runs on a database where the `raw` column already exists, THE Migration_Runner SHALL skip the rename and return success without modifying data.
6. WHEN the v5 migration runs on a database where neither `body_html` nor `raw` exists, THE Migration_Runner SHALL add the `raw` column as `TEXT NULL` and return success.
7. WHEN the v5 migration runs on a database where the `received_date` column does not yet exist, THE Migration_Runner SHALL add it as `DATETIME NULL`.
8. WHEN the v5 migration runs on a database where the `received_date` column already exists, THE Migration_Runner SHALL skip adding it and return success.
9. AFTER the v5 migration completes successfully, THE Migration_Runner SHALL record schema version 5 in the `schema_version` table.
10. WHEN any step of the v5 migration fails, THE Migration_Runner SHALL log the error and return `False` without advancing the schema version.

---

### Requirement 2: Sync Engine — Fetch Raw Source

**User Story:** As a developer, I want the sync engine to fetch the complete RFC 2822 source for each message, so that all transport headers and MIME structure are preserved in the database.

#### Acceptance Criteria

1. WHEN the Sync_Engine fetches a message from the Gmail_API, THE Sync_Engine SHALL request the message using `format=raw` instead of the default `format=full`.
2. WHEN the Gmail_API returns a base64url-encoded raw message, THE Sync_Engine SHALL decode the payload to a UTF-8 string before passing it to the Message_Parser.
3. IF the Gmail_API response does not contain a `raw` field, THEN THE Sync_Engine SHALL log a warning and store `NULL` for the `raw` column of that message.
4. WHILE a sync is in progress, THE Sync_Engine SHALL continue processing remaining messages when a single message's raw decode fails, logging the error for that message.

---

### Requirement 3: Message Parser — Parse from Raw Source

**User Story:** As a developer, I want the Message_Parser to extract headers, the plain-text body, and the received date from the stored raw RFC 2822 source, so that the structured fields used for search and display remain populated.

#### Acceptance Criteria

1. WHEN the Message_Parser receives a raw RFC 2822 string, THE Message_Parser SHALL use Python's `email` standard library to parse it into a message object.
2. WHEN parsing a raw RFC 2822 string, THE Message_Parser SHALL extract the `From`, `To`, `Cc`, `Bcc`, `Subject`, and `Date` headers from the parsed email object.
3. WHEN parsing a raw RFC 2822 string, THE Message_Parser SHALL extract the plain-text body by walking MIME parts and selecting the `text/plain` part.
4. THE Message_Parser SHALL store the full decoded RFC 2822 string in the `raw` attribute of the `Message` object.
5. IF no `text/plain` part is found in the raw source, THEN THE Message_Parser SHALL derive the plain-text body from the `text/html` part using the existing `html2text` method.
6. IF the raw source cannot be parsed by the `email` standard library, THEN THE Message_Parser SHALL raise a `MessageParsingError` with a descriptive message.
7. WHEN parsing a raw RFC 2822 string, THE Message_Parser SHALL extract `received_date` using the following precedence:
   - Parse the date from the **last** `Received:` header (the final delivery hop, closest to the recipient's mailbox). The date is the semicolon-delimited timestamp at the end of the header value, e.g. `Received: by 2002:a05:... ; Sat, 31 Jan 2026 05:37:01 -0800 (PST)`.
   - IF no `Received:` header is present or none yields a parseable date, THEN fall back to the last `X-Received:` header and parse its date using the same semicolon-delimited format.
   - IF neither `Received:` nor `X-Received:` yields a parseable date, THEN set `received_date` to `None`.
8. WHEN extracting the date from a `Received:` or `X-Received:` header, THE Message_Parser SHALL parse the substring after the final semicolon (`;`) as an RFC 2822 date string using `email.utils.parsedate_to_datetime`.
9. IF parsing the date substring raises an exception, THE Message_Parser SHALL treat that header as unparseable and continue to the next fallback, logging a debug-level warning.

---

### Requirement 4: Message Parser — Extract HTML from Raw Source

**User Story:** As a developer, I want a dedicated function to extract the displayable HTML body from a raw RFC 2822 string, so that the API can derive `body_html` on-the-fly without storing it separately.

#### Acceptance Criteria

1. THE Message_Parser SHALL expose a module-level function `extract_html_from_raw(raw: str) -> Optional[str]` that accepts a decoded RFC 2822 string and returns the `text/html` MIME part content.
2. WHEN `extract_html_from_raw` is called with a valid multipart RFC 2822 string containing a `text/html` part, THE Message_Parser SHALL return the decoded HTML string for that part.
3. WHEN `extract_html_from_raw` is called with a single-part `text/html` message, THE Message_Parser SHALL return the decoded body of that message.
4. WHEN `extract_html_from_raw` is called with a message that has no `text/html` part, THE Message_Parser SHALL return `None`.
5. WHEN `extract_html_from_raw` is called with `None` or an empty string, THE Message_Parser SHALL return `None`.
6. FOR ALL valid RFC 2822 strings that contain a `text/html` part, the HTML returned by `extract_html_from_raw` SHALL be identical to the HTML that would have been extracted by the previous `_extract_html_body` method operating on the equivalent `format=full` payload (round-trip equivalence property).

---

### Requirement 5: API Server — Serve HTML Derived from Raw

**User Story:** As a developer, I want the API server to derive and return `body_html` from the stored raw source when responding to message detail requests, so that the existing frontend rendering logic works without changes.

#### Acceptance Criteria

1. THE API_Server SHALL include `raw` in `DETAIL_FIELDS` and exclude `body_html` from the database query for `GET /api/messages/<id>`.
2. WHEN building the response for `GET /api/messages/<id>`, THE API_Server SHALL call `extract_html_from_raw` on the stored `raw` value and include the result as `body_html` in the JSON response.
3. WHEN the stored `raw` value is `NULL`, THE API_Server SHALL return `body_html: null` in the JSON response.
4. WHEN `extract_html_from_raw` returns an HTML string, THE API_Server SHALL apply the CID_Rewriter to that string before including it as `body_html` in the response.
5. THE API_Server SHALL include the `raw` field in the JSON response for `GET /api/messages/<id>` so the frontend can display it in the Source_Modal.
6. WHEN the stored `raw` value is `NULL`, THE API_Server SHALL return `raw: null` in the JSON response.

---

### Requirement 6: API Server — HTML Stripping for Display

**User Story:** As a developer, I want the API server to strip everything before the `<html` tag from the extracted HTML body, so that the iframe only receives a clean HTML document rather than raw MIME headers or preamble text.

#### Acceptance Criteria

1. WHEN the HTML extracted from the raw source contains a `<html` tag, THE HTML_Extractor SHALL return only the substring starting from the `<html` tag through the end of the string.
2. WHEN the HTML extracted from the raw source does not contain a `<html` tag, THE HTML_Extractor SHALL return the full extracted HTML string unchanged.
3. WHEN the HTML extracted from the raw source is `None` or empty, THE HTML_Extractor SHALL return `None`.

---

### Requirement 7: Frontend — View Source Link

**User Story:** As a user, I want a "View source" link in the message detail panel, so that I can inspect the complete raw RFC 2822 email including all transport headers.

#### Acceptance Criteria

1. WHEN a message detail is rendered and `msg.raw` is non-null, THE Detail_Panel SHALL display a "View source" link in the meta section of the detail panel.
2. WHEN `msg.raw` is `null` or absent, THE Detail_Panel SHALL not render the "View source" link.
3. WHEN the user clicks the "View source" link, THE Detail_Panel SHALL open the Source_Modal displaying the full raw RFC 2822 source.

---

### Requirement 8: Frontend — Source Modal

**User Story:** As a user, I want to view the complete raw email source in a readable, scrollable modal, so that I can inspect headers and MIME structure without leaving the application.

#### Acceptance Criteria

1. THE Source_Modal SHALL display the raw RFC 2822 source in a `<pre>` element using a monospace font.
2. THE Source_Modal SHALL be scrollable both vertically and horizontally to accommodate long header lines.
3. THE Source_Modal SHALL allow the user to select and copy text from the raw source.
4. THE Source_Modal SHALL provide a close button that dismisses the modal.
5. WHEN the user presses the Escape key while the Source_Modal is open, THE Source_Modal SHALL close.
6. WHEN the user clicks outside the modal content area, THE Source_Modal SHALL close.
7. THE Source_Modal SHALL be styled consistently with the existing attachment preview modal (full-screen overlay, white modal card, header with title and close button).

---

### Requirement 9: DB Layer — Persist Raw Source and Received Date

**User Story:** As a developer, I want the DB layer to save and update the `raw` and `received_date` fields correctly, so that re-syncs overwrite stale data and new messages are stored with their full source and server-side received timestamp.

#### Acceptance Criteria

1. WHEN `create_message` is called with a `Message` object, THE DB_Layer SHALL write the `raw` attribute to the `raw` column of the `messages` table.
2. WHEN `create_message` is called for a message that already exists in the database (upsert), THE DB_Layer SHALL update the `raw` column with the new value.
3. WHEN a message's `raw` attribute is `None`, THE DB_Layer SHALL store `NULL` in the `raw` column.
4. WHEN `create_message` is called with a `Message` object, THE DB_Layer SHALL write the `received_date` attribute to the `received_date` column of the `messages` table.
5. WHEN `create_message` is called for a message that already exists in the database (upsert), THE DB_Layer SHALL update the `received_date` column with the new value.
6. WHEN a message's `received_date` attribute is `None`, THE DB_Layer SHALL store `NULL` in the `received_date` column.

---

### Requirement 10: Sync Engine — Skip Already-Synced Messages

**User Story:** As a developer, I want the sync engine to identify messages that need re-syncing due to a missing raw source, so that incremental syncs are efficient while still backfilling missing data.

#### Acceptance Criteria

1. THE DB_Layer SHALL expose a function `get_message_ids_missing_raw() -> List[str]` that returns message IDs where the `raw` column is `NULL`.
2. WHEN performing a full sync, THE Sync_Engine SHALL include messages returned by `get_message_ids_missing_raw` in the set of messages to fetch, even if those messages are already present in the database.
3. THE DB_Layer SHALL remove the `get_message_ids_missing_html` function or update it to reference the `raw` column instead of `body_html`.

---

### Requirement 11: API Server — Expose Received Date

**User Story:** As a developer, I want the API server to include `received_date` in message responses, so that the frontend can use it as the authoritative display date.

#### Acceptance Criteria

1. THE API_Server SHALL include `received_date` in `SUMMARY_FIELDS` so it is returned by `GET /api/messages`.
2. THE API_Server SHALL include `received_date` in `DETAIL_FIELDS` so it is returned by `GET /api/messages/<id>`.
3. WHEN the stored `received_date` value is `NULL`, THE API_Server SHALL return `received_date: null` in the JSON response.
4. THE API_Server SHALL NOT use `received_date` for sorting — the existing `timestamp`-based `ORDER BY` clause SHALL remain unchanged.

---

### Requirement 12: Frontend — Display Received Date

**User Story:** As a user, I want the message list and detail panel to show when the message was actually received by the mail server, so that I see a reliable delivery time rather than the sender's claimed send time.

#### Acceptance Criteria

1. WHEN rendering a row in the message list, THE UI SHALL display `received_date` as the message date if `received_date` is non-null.
2. WHEN `received_date` is `null` for a message, THE UI SHALL fall back to displaying `timestamp` as the message date.
3. WHEN rendering the message detail panel, THE UI SHALL display `received_date` (or `timestamp` as fallback) as the "Date:" field in the meta section.
4. THE UI SHALL format the Display_Date using the same locale-aware formatting currently applied to `timestamp` (i.e. `new Date(...).toLocaleString()`).
5. WHEN `received_date` is shown, THE UI SHALL label it "Received:" in the detail panel meta section to distinguish it from the sender's `Date:` header.
6. WHEN only `timestamp` is available (fallback), THE UI SHALL label it "Date:" as it does today.
