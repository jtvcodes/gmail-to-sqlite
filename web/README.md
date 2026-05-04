# Gmail Web Viewer — `web/`

A Flask-based web application that provides a browser UI for reading Gmail messages stored in the local SQLite database produced by the sync tool.

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Server](#running-the-server)
- [Project Structure](#project-structure)
- [REST API Reference](#rest-api-reference)
  - [GET /api/messages](#get-apimessages)
  - [GET /api/messages/\<message\_id\>](#get-apimessagesmessage_id)
  - [GET /api/messages/\<message\_id\>/attachments/\<attachment\_id\>/data](#get-apimessagesmessage_idattachmentsattachment_iddata)
  - [GET /api/cid/\<content\_id\>](#get-apicidcontent_id)
  - [GET /api/labels](#get-apilabels)
  - [POST /api/sync](#post-apisync)
- [Frontend Architecture](#frontend-architecture)
- [Database Connection](#database-connection)
- [Running Tests](#running-tests)
- [Configuration Reference](#configuration-reference)

---

## Overview

The web module is a single-page application (SPA) backed by a Flask REST API. It reads directly from the SQLite database that the sync tool populates and exposes:

- A paginated, filterable message list
- Full message detail with HTML and plain-text body views
- Attachment download and inline preview
- A one-click sync button that triggers the sync tool from the browser

---

## Prerequisites

- Python 3.8+
- A populated SQLite database (run the sync tool first — see the root `README.md`)
- `credentials.json` in the project root (required only if you use the Sync button or attachment on-demand fetching)

---

## Installation

Install runtime dependencies from `web/requirements.txt`:

```bash
pip install -r web/requirements.txt
```

For development and testing, also install `web/requirements-dev.txt`:

```bash
pip install -r web/requirements-dev.txt
```

| File                    | Packages                          |
|-------------------------|-----------------------------------|
| `requirements.txt`      | `flask`, `flask-cors`             |
| `requirements-dev.txt`  | `pytest`, `pytest-flask`, `hypothesis` |

---

## Running the Server

Run from the **project root** (not from inside `web/`):

```bash
python -m web.server
```

Or use the entry point directly:

```bash
python web/server.py
```

### CLI Options

| Flag         | Default              | Description                                      |
|--------------|----------------------|--------------------------------------------------|
| `--port`     | `8000`               | Port the development server listens on           |
| `--db-path`  | `data/messages.db`   | Path to the SQLite database file                 |

**Examples:**

```bash
# Default — port 8000, database at data/messages.db
python -m web.server

# Custom port
python -m web.server --port 5000

# Custom database path
python -m web.server --db-path /path/to/my/messages.db
```

The server validates that the database file exists at startup and exits with an error message if it does not. Open `http://localhost:8000` in your browser once it is running.

---

## Project Structure

```
web/
├── server.py               # Application factory and CLI entry point
├── db.py                   # SQLite connection management (Flask g context)
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Development/test dependencies
├── api/
│   ├── __init__.py
│   ├── messages.py         # /api/messages endpoints
│   ├── labels.py           # /api/labels endpoint
│   └── sync.py             # /api/sync endpoint
├── static/
│   ├── index.html          # SPA shell
│   ├── app.js              # State management and bootstrap
│   ├── api.js              # Fetch wrappers for the REST API
│   ├── filters.js          # Search input and label dropdown component
│   ├── messageList.js      # Paginated message table component
│   ├── messageDetail.js    # Message detail panel component
│   └── style.css           # Application styles
└── tests/
    ├── test_web_messages.py
    ├── test_web_labels.py
    ├── test_web_properties.py
    └── ...
```

---

## REST API Reference

All endpoints are served under the `/api` prefix. Responses are JSON unless noted.

---

### GET /api/messages

Returns a paginated list of message summaries.

**Query Parameters**

| Parameter        | Type    | Default  | Description                                                                 |
|------------------|---------|----------|-----------------------------------------------------------------------------|
| `page`           | integer | `1`      | Page number (must be ≥ 1)                                                   |
| `page_size`      | integer | `50`     | Results per page (1–200)                                                    |
| `q`              | string  | —        | Full-text search across `subject`, `sender`, and `body` (case-insensitive) |
| `label`          | string  | —        | Filter by exact label name                                                  |
| `is_read`        | boolean | —        | `true` or `false`                                                           |
| `is_outgoing`    | boolean | —        | `true` or `false`                                                           |
| `include_deleted`| boolean | `false`  | Include soft-deleted messages when `true`                                   |
| `sort_dir`       | string  | `desc`   | Sort by timestamp: `asc` or `desc`                                          |

**Response**

```json
{
  "messages": [
    {
      "message_id": "18f3a...",
      "thread_id": "18f3a...",
      "sender": { "name": "Alice", "email": "alice@example.com" },
      "labels": ["INBOX", "UNREAD"],
      "subject": "Hello",
      "timestamp": "2024-01-15T10:30:00",
      "is_read": false,
      "is_outgoing": false,
      "is_deleted": false,
      "has_attachments": true
    }
  ],
  "total": 142,
  "page": 1,
  "page_size": 50
}
```

**Error Responses**

| Status | Condition                                      |
|--------|------------------------------------------------|
| `400`  | Invalid `page`, `page_size`, or boolean param  |
| `503`  | Database not yet populated (missing table)     |
| `500`  | Unexpected database error                      |

---

### GET /api/messages/\<message_id\>

Returns the full detail for a single message, including body, recipients, and attachments.

**Response**

All summary fields plus:

| Field         | Type   | Description                                      |
|---------------|--------|--------------------------------------------------|
| `body`        | string | Plain-text body                                  |
| `body_html`   | string | HTML body (with `cid:` references rewritten to `/api/cid/...`) |
| `recipients`  | object | `{ "to": [...], "cc": [...], "bcc": [...] }`     |
| `attachments` | array  | List of attachment metadata objects (see below)  |

Each attachment object:

```json
{
  "filename": "report.pdf",
  "mime_type": "application/pdf",
  "size": 204800,
  "attachment_id": "ANGjdJ...",
  "content_id": null
}
```

**Error Responses**

| Status | Condition                  |
|--------|----------------------------|
| `404`  | Message not found          |
| `503`  | Database not ready         |
| `500`  | Unexpected database error  |

---

### GET /api/messages/\<message_id\>/attachments/\<attachment_id\>/data

Serves the raw bytes of an attachment.

**Query Parameters**

| Parameter | Type    | Description                                                    |
|-----------|---------|----------------------------------------------------------------|
| `preview` | `"1"`   | Sets `Content-Disposition: inline` so the browser renders it  |

**Resolution order:**

1. Disk cache at `data/attachments/<message_id>/<filename>`
2. `data` column in the `attachments` table (legacy inline storage)
3. On-demand fetch from the Gmail API (requires valid `credentials.json`)

Fetched attachments are cached to disk automatically for subsequent requests.

**Error Responses**

| Status | Condition                                  |
|--------|--------------------------------------------|
| `404`  | Attachment record not found                |
| `502`  | Gmail API fetch failed                     |
| `500`  | Unexpected error                           |

---

### GET /api/cid/\<content_id\>

Resolves a `cid:` inline image reference used in HTML email bodies.

**Query Parameters**

| Parameter | Type   | Description                                          |
|-----------|--------|------------------------------------------------------|
| `msg`     | string | Message ID — scopes the lookup and avoids collisions |

Internally delegates to the same resolution logic as the attachment data endpoint.

---

### GET /api/labels

Returns a sorted list of all distinct labels present on non-deleted messages.

**Response**

```json
["INBOX", "SENT", "STARRED", "UNREAD", "work"]
```

---

### POST /api/sync

Triggers an incremental sync by running `python main.py sync --data-dir ./data` as a subprocess. The request blocks until the sync completes (up to 5 minutes).

**Response (success)**

```json
{ "ok": true, "output": "Synced 12 new messages." }
```

**Response (failure)**

```json
{ "error": "..." }
```

| Status | Condition                          |
|--------|------------------------------------|
| `500`  | `main.py` not found or sync failed |
| `504`  | Sync timed out after 5 minutes     |

---

## Frontend Architecture

The SPA is built with vanilla JavaScript — no framework or build step required. Each file has a single responsibility:

| File               | Responsibility                                                                 |
|--------------------|--------------------------------------------------------------------------------|
| `app.js`           | Global `state` object, loading overlay, error banner, bootstrap on `DOMContentLoaded` |
| `api.js`           | Thin `fetch` wrappers (`fetchMessages`, `fetchMessage`, `fetchLabels`); exports `api` object |
| `filters.js`       | Renders the search input and label `<select>` into `#filter-bar`; exports `filters` |
| `messageList.js`   | Renders the sortable, paginated message table into `#message-list`; exports `messageList` |
| `messageDetail.js` | Renders the detail panel into `#message-detail`, handles HTML/text toggle and attachment preview; exports `messageDetail` |

### State Object (`app.js`)

All UI state lives in a single `state` object:

```js
{
  messages: [],        // Current page of message summaries
  total: 0,            // Total matching messages (for pagination)
  page: 1,
  pageSize: 50,
  query: "",           // Full-text search string
  label: "",           // Active label filter
  isRead: null,        // true | false | null (no filter)
  isOutgoing: null,
  includeDeleted: false,
  selectedMessage: null,
  labels: [],          // All available labels (for dropdown)
  error: null,
  sortDir: "desc",     // "asc" | "desc"
}
```

Components read from `state` and call `state.onFilterChange()` to trigger a reload.

### Message Body Rendering

`messageDetail.js` renders the body inside a sandboxed `<iframe>` to isolate email HTML from the application. Two views are available:

- **HTML view** — uses `body_html` if present; falls back to `body` rendered as pre-formatted text.
- **Plain text view** — uses `body`, HTML-escaped and with URLs linkified.

A toggle switch switches between views without re-fetching the message.

---

## Database Connection

`web/db.py` manages the SQLite connection using Flask's application context (`g`):

- `get_db()` — opens a connection on first call within a request context, reuses it on subsequent calls. Rows are accessible by column name via `sqlite3.Row`.
- `close_db()` — registered as a teardown handler; closes the connection at the end of each request.

The database path is set once in `app.config["DB_PATH"]` when the app is created and never changes at runtime.

---

## Running Tests

Tests use `pytest` and `hypothesis` (property-based testing). Run from the **project root**:

```bash
# Run all web tests
pytest web/tests/

# Run a specific test file
pytest web/tests/test_web_messages.py

# Run with verbose output
pytest web/tests/ -v

# Run property-based tests only
pytest web/tests/test_web_properties.py
```

Test files:

| File                                    | What it covers                                      |
|-----------------------------------------|-----------------------------------------------------|
| `test_web_messages.py`                  | Message list and detail endpoint behaviour          |
| `test_web_labels.py`                    | Labels endpoint                                     |
| `test_web_properties.py`                | Property-based tests for the messages API           |
| `test_message_html_view.py`             | HTML/text body rendering logic                      |
| `test_message_html_view_properties.py`  | Property-based tests for body rendering             |
| `test_raw_body_storage_web_properties.py` | Raw body storage round-trip properties            |
| `test_preservation_properties.py`       | Data preservation invariants                        |
| `test_recipient_formatting.py`          | Recipient object formatting                         |
| `test_bug_condition.py`                 | Regression / bug condition tests                    |

---

## Configuration Reference

| Config key  | Set by          | Description                          |
|-------------|-----------------|--------------------------------------|
| `DB_PATH`   | `create_app()`  | Absolute or relative path to the SQLite database |

There are no environment variables required for normal operation. The Gmail API credentials (`credentials.json`) are only needed when the server needs to fetch attachments on demand or when the Sync button is used.
