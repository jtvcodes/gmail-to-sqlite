# Implementation Plan: Gmail Web Viewer

## Overview

Build a Flask-backed SPA that reads from the existing `data/messages.db` SQLite database and serves a vanilla JS frontend for browsing, searching, and reading Gmail messages. All new code lives under `web/` and `tests/`.

## Tasks

- [x] 1. Create the `web/` directory structure and declare dependencies
  - Create `web/requirements.txt` with `flask` and `flask-cors`
  - Create `web/requirements-dev.txt` with `pytest`, `pytest-flask`, and `hypothesis`
  - Create the directory skeleton: `web/api/`, `web/static/`, `web/tests/`
  - Create empty placeholder files: `web/api/__init__.py`, `web/api/messages.py`, `web/api/labels.py`, `web/db.py`, `web/server.py`, `web/tests/__init__.py`
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Implement the database helper and Flask server entry point
  - [ ] 2.1 Implement `web/db.py`: `get_db()` opens a `sqlite3.Connection` (row_factory=sqlite3.Row) using the DB path stored in `app.config["DB_PATH"]`; `close_db()` tears it down after each request
  - [ ] 2.2 Parse CLI arguments in `web/server.py` (`--port` defaulting to `8000`, `--db-path` defaulting to `data/messages.db`)
  - [ ] 2.3 Validate that the DB file exists at startup; print a descriptive error to stderr and `sys.exit(1)` if not
  - [ ] 2.4 Store DB path in `app.config["DB_PATH"]` and register `close_db` with `app.teardown_appcontext`
  - [ ] 2.5 Register the messages and labels blueprints under `/api`
  - [ ] 2.6 Serve `web/static/` as static files and route `GET /` to `index.html`
  - [ ] 2.7 Start the Flask development server on the configured port
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. Implement the messages API blueprint (`web/api/messages.py`)
  - [x] 3.1 Implement `GET /api/messages` with pagination (`page`, `page_size`), returning the response envelope `{messages, total, page, page_size}`
    - Validate `page` ≥ 1 and `page_size` in 1–200; return HTTP 400 on invalid values
    - Exclude `is_deleted=true` records by default; honour `include_deleted=true` when provided
    - Order results by `timestamp` descending
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.1, 6.2, 7.3_
  - [x] 3.2 Add search filter (`q`) — case-insensitive substring match on `subject`, `sender` JSON text, and `body`
    - _Requirements: 3.1_
  - [x] 3.3 Add label filter (`label`) — exact match within the `labels` JSON array
    - _Requirements: 3.2_
  - [x] 3.4 Add boolean filters (`is_read`, `is_outgoing`) — accept `"true"` / `"false"` strings
    - _Requirements: 3.3, 3.4_
  - [x] 3.5 Implement `GET /api/messages/<message_id>` returning the full message record (summary fields + `recipients`, `body`); return HTTP 404 with `{"error": "Message not found"}` if absent
    - _Requirements: 4.1, 4.2_
  - [x] 3.6 Write unit tests for `GET /api/messages` parameter validation and filter logic (`web/tests/test_web_messages.py`)
    - Test invalid `page` / `page_size` values return HTTP 400
    - Test each filter (`q`, `label`, `is_read`, `is_outgoing`, `include_deleted`) in isolation against a seeded in-memory DB
    - Test response envelope fields (`total`, `page`, `page_size`) are present and correct
    - _Requirements: 2.1–2.5, 3.1–3.4, 6.1, 7.3_
  - [x] 3.7 Write unit tests for `GET /api/messages/<message_id>` (`web/tests/test_web_messages.py`)
    - Test 200 response with all required fields for an existing message
    - Test 404 response for a non-existent `message_id`
    - _Requirements: 4.1, 4.2_

- [x] 4. Implement the labels API blueprint (`web/api/labels.py`)
  - [x] 4.1 Implement `GET /api/labels` — query distinct labels from non-deleted messages, flatten the JSON arrays, deduplicate, and return sorted alphabetically
    - _Requirements: 5.1_
  - [x] 4.2 Write unit tests for `GET /api/labels` (`web/tests/test_web_labels.py`)
    - Test that only labels from non-deleted messages are returned
    - Test that the result is sorted alphabetically and deduplicated
    - _Requirements: 5.1_

- [x] 5. Checkpoint — Ensure all backend tests pass
  - Run `pytest web/tests/test_web_messages.py web/tests/test_web_labels.py -v` and confirm all tests pass; resolve any failures before continuing.

- [x] 6. Write property-based tests for the messages API (`web/tests/test_web_properties.py`)
  - [x] 6.1 Write property test for pagination total consistency
    - **Property 1: Pagination total consistency**
    - **Validates: Requirements 2.5**
    - Use `hypothesis` strategies to generate random filter combos; assert `total` equals a direct count query with the same filters
  - [x] 6.2 Write property test for page size bounds
    - **Property 2: Page size bounds**
    - **Validates: Requirements 2.2**
    - Generate random `page` and `page_size` values; assert `len(messages) <= page_size` and `len(messages) <= total`
  - [x] 6.3 Write property test for search filter soundness
    - **Property 3: Search filter soundness**
    - **Validates: Requirements 3.1**
    - Generate random query strings and seeded message sets; assert every returned message contains the query in `subject`, `sender.name`, `sender.email`, or `body`
  - [x] 6.4 Write property test for label filter soundness
    - **Property 4: Label filter soundness**
    - **Validates: Requirements 3.2**
    - Generate random label strings and seeded message sets; assert every returned message has that label in its `labels` array
  - [x] 6.5 Write property test for boolean filter soundness
    - **Property 5: Boolean filter soundness**
    - **Validates: Requirements 3.3, 3.4**
    - Generate random `is_read` / `is_outgoing` boolean values and message sets; assert all returned messages match the filter
  - [x] 6.6 Write property test for deleted messages excluded by default
    - **Property 6: Deleted messages excluded by default**
    - **Validates: Requirements 6.1**
    - Generate message sets with mixed `is_deleted` values; assert no returned message has `is_deleted=True` when `include_deleted` is not set
  - [x] 6.7 Write property test for labels endpoint completeness
    - **Property 7: Labels endpoint completeness**
    - **Validates: Requirements 5.1**
    - Generate random message sets; assert every label from non-deleted messages appears in `GET /api/labels` and the list is sorted
  - [x] 6.8 Write property test for invalid pagination parameters rejected
    - **Property 8: Invalid pagination parameters rejected**
    - **Validates: Requirements 7.3**
    - Generate invalid `page` / `page_size` values (zero, negative, non-numeric strings); assert HTTP 400 is returned

- [x] 7. Checkpoint — Ensure all property tests pass
  - Run `pytest web/tests/test_web_properties.py -v` and confirm all property tests pass; resolve any failures before continuing.

- [x] 8. Build the frontend shell (`web/static/index.html` and `web/static/style.css`)
  - [x] 8.1 Create `web/static/index.html` with the page shell: header, filter bar placeholder, message list table placeholder, detail panel placeholder, and error banner placeholder; import `style.css`, `api.js`, `filters.js`, `messageList.js`, `messageDetail.js`, and `app.js`
    - _Requirements: 2.6, 3.5, 3.6, 4.3, 4.4, 4.5_
  - [x] 8.2 Create `web/static/style.css` with minimal styles: table layout, unread/read row distinction, deleted message strikethrough/muted style, detail panel, error banner, and pagination controls
    - _Requirements: 2.6, 6.3_

- [x] 9. Implement the frontend API client (`web/static/api.js`)
  - Implement `fetchMessages(params)` — builds query string from state params and calls `GET /api/messages`
  - Implement `fetchMessage(messageId)` — calls `GET /api/messages/{messageId}`
  - Implement `fetchLabels()` — calls `GET /api/labels`
  - On non-2xx responses, extract `error` from JSON body (or fall back to status text) and throw an `Error`; on network failure throw with the generic message
  - _Requirements: 2.1, 4.1, 5.2, 7.1_

- [x] 10. Implement the filters component (`web/static/filters.js`)
  - Render the search input field and wire its `submit` / `input` event to update `state.query` and call `state.onFilterChange()`
  - Render the label dropdown and populate it from `state.labels`; wire `change` event to update `state.label` and call `state.onFilterChange()`
  - Reset `state.page` to `1` whenever any filter changes
  - _Requirements: 3.5, 3.6, 3.7_

- [x] 11. Implement the message list component (`web/static/messageList.js`)
  - Render the message table with columns: sender name/email, subject, date, read/unread indicator
  - Apply a CSS class for unread rows and a separate class for deleted rows (strikethrough/muted)
  - Render pagination controls (previous/next buttons and current page indicator); wire clicks to update `state.page` and re-fetch
  - Wire row clicks to call `state.onMessageSelect(messageId)`
  - _Requirements: 2.6, 2.7, 2.8, 6.3_

- [x] 12. Implement the message detail component (`web/static/messageDetail.js`)
  - Render the detail panel/modal showing: subject, sender name and email, recipient list (to, cc, bcc), date/time, labels, and body text
  - Render a close/dismiss button that clears `state.selectedMessage` and re-renders the list view
  - _Requirements: 4.3, 4.4, 4.5_

- [x] 13. Implement the app bootstrap and state management (`web/static/app.js`)
  - Define the global `state` object matching the shape in the design document
  - Implement `loadMessages()` — calls `api.fetchMessages(state)`, updates `state.messages` / `state.total`, clears errors, and calls `messageList.render()`
  - Implement `loadLabels()` — calls `api.fetchLabels()`, updates `state.labels`, and calls `filters.render()`
  - Implement `selectMessage(messageId)` — calls `api.fetchMessage(messageId)`, updates `state.selectedMessage`, and calls `messageDetail.render()`
  - Wire `state.onFilterChange` to reset page and call `loadMessages()`
  - Wire `state.onMessageSelect` to call `selectMessage()`
  - On any API error, set `state.error` and render the error banner; clear it on the next successful fetch
  - On `DOMContentLoaded`, call `loadLabels()` then `loadMessages()`
  - _Requirements: 2.8, 3.5, 3.6, 3.7, 4.3, 5.2, 7.1_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Run `pytest web/tests/ -v` and confirm the full test suite passes; resolve any failures before finishing.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- All property tests use an in-memory SQLite database seeded by Hypothesis strategies — `data/messages.db` is never touched during tests
- Each property test task references a specific property from the design document for traceability
- Checkpoints ensure incremental validation after each major layer
