# Implementation Plan: raw-message-source

## Overview

Replace the `body_html` column with a `raw` column storing the complete RFC 2822 email source, add a `received_date` column, derive HTML on-the-fly at API response time, and expose a "View source" modal in the frontend. The implementation follows a strict bottom-up order: schema → parser → DB layer → sync engine → API server → frontend → CSS → property tests.

## Tasks

- [x] 1. Schema migration v5 — rename `body_html` to `raw` and add `received_date`
  - Create `gmail_to_sqlite/schema_migrations/v5_rename_body_html_to_raw.py` with a `run()` function that handles all five database states described in the design (body_html exists, raw already exists, neither exists, received_date absent, received_date already exists)
  - Use `column_exists()` from the existing migrations helper for all guards
  - Use `ALTER TABLE messages RENAME COLUMN body_html TO raw` (SQLite ≥ 3.25) for the rename path
  - Use `ALTER TABLE messages ADD COLUMN raw TEXT` for the add-column path
  - Use `ALTER TABLE messages ADD COLUMN received_date DATETIME` for the received_date path
  - Return `True` on success, catch all exceptions, log the error, and return `False` on any failure
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.10_

  - [x] 1.1 Wire v5 migration into the migration runner
    - In `gmail_to_sqlite/migrations.py`, add an `if current_version == 4:` block that imports and calls `run_v5`, sets schema version to 5, and returns `False` on any failure — following the exact pattern of the existing v1–v4 blocks
    - Update the final idle-log guard from `current_version >= 4` to `current_version >= 5`
    - _Requirements: 1.3, 1.9_

  - [x] 1.2 Write unit tests for v5 migration
    - In `tests/test_v5_migration.py`, test: rename from body_html to raw preserves data; no-op when raw already exists; add column when neither exists; received_date added when absent; no-op when received_date already exists; schema version set to 5 after success; `False` returned on simulated failure
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

- [x] 2. Message parser — `from_raw_source` factory, `extract_html_from_raw`, `_parse_received_date`, `received_date` attribute
  - In `gmail_to_sqlite/message.py`:
    - Replace the `body_html: Optional[str]` attribute with `raw: Optional[str] = None`
    - Add `received_date: Optional[datetime] = None` attribute
    - Add `_parse_received_date(parsed_email) -> Optional[datetime]` private method: iterate `received` then `x-received` headers in reverse order (last header = final delivery hop), split on `;`, parse the trailing date string with `parsedate_to_datetime`, log debug on parse failure, return `None` if no header yields a date
    - Add `extract_html_from_raw(raw: str) -> Optional[str]` as a **module-level function**: return `None` for `None`/empty input; use `email.message_from_string` to parse; walk MIME parts to find the first `text/html` part; decode its payload; apply `_strip_to_html_tag` before returning
    - Add `_strip_to_html_tag(html: str) -> Optional[str]` as a module-level helper: return `None` for `None`/empty; if `<html` is present return the substring from `<html` onward; otherwise return the string unchanged
    - Add `from_raw_source(cls, raw_str: str, labels: Dict[str, str]) -> "Message"` classmethod: parse the RFC 2822 string with `email.message_from_string`; extract `From`, `To`, `Cc`, `Bcc`, `Subject`, `Date` headers; extract plain-text body by walking MIME parts for `text/plain`, falling back to `html2text` on `text/html`; set `msg.raw = raw_str`; call `_parse_received_date`; raise `MessageParsingError` on failure
    - Keep the existing `from_raw` classmethod and `parse` method intact (they are still used by `single_message` and tests)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 4.5, 6.1, 6.2, 6.3_

  - [x] 2.1 Write property test — Property 3: Base64url decode round-trip
    - In `tests/test_raw_message_source_properties.py`, add `test_base64url_decode_roundtrip` using `@given(st.text())` `@settings(max_examples=200)`: base64url-encode the text, then decode it with the sync engine's decode path, assert equality
    - **Property 3: Base64url decode round-trip**
    - **Validates: Requirements 2.2**

  - [x] 2.2 Write property test — Property 4: Message parse preserves raw, headers, and received_date
    - In `tests/test_raw_message_source_properties.py`, add `test_parse_preserves_raw_headers_and_received_date` using a `rfc2822_message_strategy()` composite strategy that generates valid RFC 2822 strings with random `From`, `To`, `Subject`, `Date`, and at least one `Received:` header with a semicolon-delimited date; assert `msg.raw == input`, header fields match, `msg.received_date` equals the datetime from the last `Received:` header
    - **Property 4: Message parse preserves raw, headers, and received_date**
    - **Validates: Requirements 3.2, 3.4, 3.7**

  - [x] 2.3 Write property test — Property 5: HTML extraction round-trip
    - In `tests/test_raw_message_source_properties.py`, add `test_html_extraction_roundtrip` using `@given(st.text(min_size=1))` `@settings(max_examples=100)`: build a minimal RFC 2822 multipart/alternative message embedding the HTML string as the `text/html` part; call `extract_html_from_raw`; assert the returned HTML equals the original (after accounting for MIME encoding/decoding)
    - **Property 5: HTML extraction round-trip**
    - **Validates: Requirements 4.2**

  - [x] 2.4 Write property test — Property 7: HTML stripping correctness
    - In `tests/test_raw_message_source_properties.py`, add `test_html_stripping` using `@given(st.text(), st.text())` `@settings(max_examples=200)`: for `preamble + "<html" + body`, assert result starts with `<html`; for strings without `<html`, assert result equals input unchanged
    - **Property 7: HTML stripping correctness**
    - **Validates: Requirements 6.1, 6.2**

  - [x] 2.5 Write property test — Property 13: received_date uses last Received header
    - In `tests/test_raw_message_source_properties.py`, add `test_received_date_uses_last_header` using `@given(st.lists(st.datetimes(timezones=st.just(timezone.utc)), min_size=2, max_size=5))` `@settings(max_examples=100)`: build an RFC 2822 string with multiple `Received:` headers each containing a semicolon-delimited date; assert `_parse_received_date` returns the datetime from the **last** header in document order
    - **Property 13: received_date extraction — last Received header used**
    - **Validates: Requirements 3.7**

  - [x] 2.6 Write property test — Property 14: received_date fallback to X-Received
    - In `tests/test_raw_message_source_properties.py`, add `test_received_date_fallback_to_x_received` using `@given(st.datetimes(timezones=st.just(timezone.utc)))` `@settings(max_examples=100)`: build an RFC 2822 string with no `Received:` header but one `X-Received:` header with a valid date; assert `_parse_received_date` returns that date
    - **Property 14: received_date fallback to X-Received**
    - **Validates: Requirements 3.7**

  - [x] 2.7 Write unit tests for message parser
    - In `tests/test_message.py`, add tests for: `extract_html_from_raw` with known multipart message; returns `None` for plain-text-only; returns `None` for `None` input; `_strip_to_html_tag` with preamble before `<html`; `_strip_to_html_tag` with no `<html` tag; `from_raw_source` extracts correct headers; fallback to `html2text` when no `text/plain`; `received_date` from last `Received:` header; fallback to `X-Received:`; `None` when neither present; `None` when no semicolon; `None` when date substring is malformed
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 4.5, 6.1, 6.2, 6.3_

- [x] 3. Checkpoint — parser and migration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. DB layer — `raw` + `received_date` fields, `get_message_ids_missing_raw`
  - In `gmail_to_sqlite/db.py`:
    - In the `Message` ORM model, replace `body_html = TextField(null=True)` with `raw = TextField(null=True)` and add `received_date = DateTimeField(null=True)`
    - In `create_message`, replace `body_html=msg.body_html` with `raw=msg.raw` in the `insert()` call; add `received_date=msg.received_date` to the `insert()` call; replace `Message.body_html: msg.body_html` with `Message.raw: msg.raw` in the `on_conflict(update={...})` dict; add `Message.received_date: msg.received_date` to the same dict
    - Add `get_message_ids_missing_raw() -> List[str]` function that queries `Message.raw.is_null(True)` — mirrors the structure of the existing `get_message_ids_missing_html`
    - Remove (or rename) `get_message_ids_missing_html` — update its docstring/name to reference `raw` per Requirement 10.3; if removing, ensure no other callers remain
  - _Requirements: 1.1, 1.2, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 10.1, 10.3_

  - [x] 4.1 Write property test — Property 9: DB raw and received_date round-trip
    - In `tests/test_raw_message_source_properties.py`, add `test_db_raw_and_received_date_roundtrip` using `@given(st.one_of(st.none(), st.text()), st.one_of(st.none(), st.datetimes()))` `@settings(max_examples=100)`: call `create_message` with a `Message` object carrying the generated `raw` and `received_date`; query the DB; assert stored values match; call again with different values; assert stored values are updated (upsert)
    - **Property 9: DB raw and received_date round-trip**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**

  - [x] 4.2 Write property test — Property 10: `get_message_ids_missing_raw` completeness
    - In `tests/test_raw_message_source_properties.py`, add `test_missing_raw_completeness` using `@given(st.lists(st.one_of(st.none(), st.text(min_size=1))))` `@settings(max_examples=100)`: insert messages with the generated mix of `NULL` and non-null `raw` values; call `get_message_ids_missing_raw()`; assert the returned set equals exactly the IDs of messages where `raw` was `None`
    - **Property 10: get_message_ids_missing_raw completeness**
    - **Validates: Requirements 10.1**

  - [x] 4.3 Write unit tests for DB layer
    - In `tests/test_db.py`, add tests for: `get_message_ids_missing_raw` returns correct IDs; `create_message` writes `raw` column; `create_message` writes `received_date` column; upsert updates both `raw` and `received_date`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 10.1_

- [x] 5. Sync engine — `format=raw`, base64url decode, call `from_raw_source`
  - In `gmail_to_sqlite/sync.py`:
    - In `_fetch_message`, add `format='raw'` to the `service.users().messages().get(userId="me", id=message_id)` call
    - After receiving `raw_msg`, check for the `'raw'` key: if absent, log a `WARNING` and create a `Message` object with `msg.raw = None` (or call `from_raw_source` with an empty/sentinel value that sets raw to None); if present, decode `raw_msg['raw']` with `base64.urlsafe_b64decode(...).decode('utf-8')` inside a try/except — on decode failure log the error and set `msg.raw = None`
    - Replace the call `message.Message.from_raw(raw_msg, labels)` with `message.Message.from_raw_source(decoded_str, labels)` when decoding succeeds
    - In `all_messages`, replace `db.get_message_ids_missing_html()` with `db.get_message_ids_missing_raw()` and update the log message to reference `raw`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 10.2_

  - [x] 5.1 Write unit tests for sync engine changes
    - In `tests/test_sync.py` (or equivalent), add tests for: `_fetch_message` passes `format='raw'` to the API call; decodes base64url payload and calls `from_raw_source`; logs warning and sets `raw=None` when `'raw'` key absent; logs error and sets `raw=None` when base64url decode fails; `all_messages` calls `get_message_ids_missing_raw` not `get_message_ids_missing_html`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 10.2_

- [x] 6. Checkpoint — backend pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. API server — `SUMMARY_FIELDS` + `received_date`, `DETAIL_FIELDS` with `raw` not `body_html`, derive `body_html` on-the-fly
  - In `web/api/messages.py`:
    - Add `'received_date'` to `SUMMARY_FIELDS` tuple
    - In `DETAIL_FIELDS`, remove `'body_html'` and add `'raw'`; `'received_date'` is inherited from `SUMMARY_FIELDS`
    - At the top of the file, add `from gmail_to_sqlite.message import extract_html_from_raw`
    - In `get_message`, after building `msg_dict` from the DB row: call `extract_html_from_raw(msg_dict.get('raw') or '')` to derive `body_html`; apply the existing CID rewriter regex to the derived `body_html` (move/reuse the existing `re.sub` block); set `msg_dict['body_html'] = body_html`; wrap the extraction in a try/except — on exception log the error and set `msg_dict['body_html'] = None`
    - The `raw` and `received_date` fields are already in `msg_dict` from the DB query; pass them through unchanged
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 11.1, 11.2, 11.3, 11.4_

  - [x] 7.1 Write property test — Property 8: API response body_html derivation
    - In `tests/test_raw_message_source_properties.py`, add `test_api_body_html_derivation` using `@given(rfc2822_with_html_strategy())` `@settings(max_examples=100)`: insert a message with a generated `raw` value into the test DB; call `GET /api/messages/<id>` via the Flask test client; assert `response.json['body_html']` equals `extract_html_from_raw(raw)` after CID rewriting
    - **Property 8: API response body_html derivation**
    - **Validates: Requirements 5.2, 5.4**

  - [x] 7.2 Write unit tests for API server changes
    - In `tests/test_api_messages.py`, add tests for: `GET /api/messages/<id>` returns `body_html` derived from `raw`; returns `body_html: null` when `raw` is NULL; returns `raw` field in response; returns `raw: null` when raw is NULL; returns `received_date` when present; returns `received_date: null` when absent; `GET /api/messages` includes `received_date` in summary rows; CID rewriting applied to derived `body_html`; `DETAIL_FIELDS` contains `raw` and not `body_html`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 11.1, 11.2, 11.3_

- [x] 8. Frontend — `messageList.js` display date
  - In `web/static/messageList.js`:
    - Add a module-level helper `function getDisplayDate(msg) { return msg.received_date || msg.timestamp; }` near the top of the file
    - In the date cell rendering block, replace `message.timestamp` with `getDisplayDate(message)` so the list shows `received_date` when available, falling back to `timestamp`
    - The `new Date(...).toLocaleString()` formatting call remains unchanged
  - _Requirements: 12.1, 12.2, 12.4_

  - [x] 8.1 Write property test — Property 15: Display date uses received_date when available (fast-check/Jest)
    - In `tests/test_messageDetail.test.js` (or `tests/test_messageList.test.js`), add `test_display_date_prefers_received_date` using fast-check `fc.property(fc.option(fc.string({ minLength: 1 })), fc.string({ minLength: 1 }), ...)`: for `received_date` non-null assert `getDisplayDate` returns `received_date`; for `received_date` null/undefined assert `getDisplayDate` returns `timestamp`
    - **Property 15: Display date uses received_date when available**
    - **Validates: Requirements 12.1, 12.2**

- [x] 9. Frontend — `messageDetail.js` received/date label, "View source" link, source modal
  - In `web/static/messageDetail.js`:
    - In the `render()` function, replace the single `dateLine` block with conditional logic: if `msg.received_date` is non-null, create a `<div>` with text `"Received: " + new Date(msg.received_date).toLocaleString()`; otherwise create a `<div>` with text `"Date: " + new Date(msg.timestamp).toLocaleString()` (existing behaviour)
    - After the Gmail link block, add a conditional block: if `msg.raw` is non-null and non-empty, create an `<a>` element with text "View source", `href="#"`, `className="detail-view-source-link"`, and an `addEventListener('click', ...)` that calls `event.preventDefault()` then `openSourceModal(msg.raw)`; append it to `meta`
    - Add `openSourceModal(rawSource)` function following the same structure as `openAttachmentPreview`: full-screen overlay (`id="source-modal-overlay"`, `className="source-modal-overlay"`); close on backdrop click; white modal card (`className="source-modal"`); header div with title span "Message Source" and close button (✕, `className="source-modal-close"`); body div containing a `<pre>` element (`className="source-modal-pre"`) whose `textContent` is set to `rawSource`; Escape key listener with cleanup on remove
    - Export `openSourceModal` on the `messageDetail` object for testability
  - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 12.3, 12.4, 12.5, 12.6_

  - [x] 9.1 Write property test — Property 11: View source link presence (fast-check/Jest)
    - In `tests/test_messageDetail.test.js`, add `test_view_source_link_presence` using fast-check `fc.property(fc.string({ minLength: 1 }), ...)`: for `msg.raw` non-null/non-empty assert the rendered panel contains a `.detail-view-source-link` element; for `msg.raw` null/undefined assert no such element exists
    - **Property 11: View source link presence**
    - **Validates: Requirements 7.1, 7.2**

  - [x] 9.2 Write property test — Property 12: Source modal displays raw content (fast-check/Jest)
    - In `tests/test_messageDetail.test.js`, add `test_source_modal_displays_raw_content` using fast-check `fc.property(fc.string(), ...)`: call `openSourceModal(rawStr)`; assert the DOM contains a `.source-modal-pre` element whose `textContent` equals `rawStr`
    - **Property 12: Source modal displays raw content**
    - **Validates: Requirements 8.1**

  - [x] 9.3 Write unit tests for messageDetail.js
    - In `tests/test_messageDetail.test.js`, add tests for: "View source" link rendered when `msg.raw` non-null; link absent when `msg.raw` null; Source_Modal opens on click; Source_Modal closes on Escape; Source_Modal closes on backdrop click; `<pre>` contains raw string; detail panel shows "Received:" label when `msg.received_date` non-null; detail panel shows "Date:" label when `msg.received_date` null
    - _Requirements: 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 12.3, 12.5, 12.6_

  - [x] 9.4 Write unit tests for messageList.js
    - In `tests/test_messageList.test.js`, add tests for: message list uses `received_date` when non-null; message list falls back to `timestamp` when `received_date` null
    - _Requirements: 12.1, 12.2_

- [x] 10. CSS — source modal styles
  - In `web/static/style.css`, append styles for the source modal following the same visual pattern as `.attachment-preview-overlay` / `.attachment-preview-modal`:
    - `.source-modal-overlay`: `position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 300; display: flex; align-items: center; justify-content: center; padding: 24px`
    - `.source-modal`: `background: #fff; border-radius: 8px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); display: flex; flex-direction: column; width: 90vw; max-width: 960px; height: 85vh; overflow: hidden`
    - `.source-modal-header`: `display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid #eee; flex-shrink: 0`
    - `.source-modal-title`: `font-size: 14px; font-weight: 500; color: #333`
    - `.source-modal-close`: `background: none; border: none; font-size: 18px; cursor: pointer; color: #666; line-height: 1; padding: 4px 8px` (hover: `color: #333`)
    - `.source-modal-body`: `flex: 1; overflow: auto; padding: 16px; background: #f8f8f8`
    - `.source-modal-pre`: `margin: 0; font-family: monospace; font-size: 12px; white-space: pre; overflow: auto; color: #333; line-height: 1.5; user-select: text`
    - `.detail-view-source-link`: `display: inline-flex; align-items: center; color: #1a73e8; text-decoration: none; font-size: 13px; margin-top: 4px; cursor: pointer` (hover: `text-decoration: underline`)
  - _Requirements: 8.1, 8.2, 8.3, 8.7_

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The implementation order is strictly bottom-up: schema → parser → DB → sync → API → frontend → CSS
- Property tests (Hypothesis backend, fast-check/Jest frontend) are placed immediately after the implementation tasks they validate
- The existing `from_raw` classmethod and `parse` method in `message.py` must remain intact — `single_message` in `sync.py` and existing tests depend on them
- `get_message_ids_missing_html` in `db.py` should be removed or renamed; verify no other callers exist before deleting
- The `_strip_to_html_tag` helper and `extract_html_from_raw` are module-level functions (not methods) so the API server can import them directly
- Property 6 (HTML extraction equivalence with old method) is covered by the unit tests in task 2.7 rather than a separate property test, since it requires constructing equivalent `format=full` payloads which is better expressed as a parameterised example test
