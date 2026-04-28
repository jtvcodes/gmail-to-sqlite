# Requirements Document

## Introduction

A simple Single Page Application (SPA) for browsing Gmail messages stored in a local SQLite database (`data/messages.db`). The app consists of a lightweight Python backend (Flask or FastAPI) that exposes a REST API over the database, and a vanilla JS frontend that renders a message list with click-to-read and basic search/filter capabilities. The entire app lives under a new `web/` folder in the workspace root.

## Glossary

- **API_Server**: The Python backend process that reads from the SQLite database and serves JSON responses.
- **SPA**: The Single Page Application running in the browser; communicates with the API_Server via HTTP.
- **Message**: A single email record stored in the `messages` table of the SQLite database.
- **Message_List**: The paginated, filterable view of all Messages shown in the SPA.
- **Message_Detail**: The full content view of a single Message shown when the user clicks a row in the Message_List.
- **Search_Query**: A free-text string entered by the user to filter Messages by subject, sender, or body.
- **Label_Filter**: A label string selected by the user to restrict the Message_List to Messages carrying that label.
- **DB_Path**: The file-system path to the SQLite database, defaulting to `data/messages.db` relative to the workspace root.

---

## Requirements

### Requirement 1: Start the API Server

**User Story:** As a developer, I want to start the API server with a single command, so that I can serve the SPA and database API locally without complex setup.

#### Acceptance Criteria

1. THE API_Server SHALL expose an HTTP server on a configurable port, defaulting to `8000`.
2. WHERE a `--db-path` argument is provided at startup, THE API_Server SHALL use that path as DB_Path instead of the default.
3. THE API_Server SHALL serve the SPA's static files (HTML, CSS, JS) from `web/static/` so that navigating to `http://localhost:8000/` returns the SPA.
4. IF the file at DB_Path does not exist at startup, THEN THE API_Server SHALL exit with a non-zero status code and print a descriptive error message.

---

### Requirement 2: List Messages

**User Story:** As a user, I want to see a paginated list of my email messages, so that I can browse my inbox without loading everything at once.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `GET /api/messages` endpoint that returns a JSON array of Message summaries.
2. THE `GET /api/messages` endpoint SHALL support a `page` query parameter (integer, default `1`) and a `page_size` query parameter (integer, default `50`, maximum `200`).
3. THE `GET /api/messages` endpoint SHALL return each Message summary with the fields: `message_id`, `thread_id`, `sender`, `labels`, `subject`, `timestamp`, `is_read`, `is_outgoing`, `is_deleted`.
4. THE `GET /api/messages` endpoint SHALL return Messages ordered by `timestamp` descending by default.
5. THE `GET /api/messages` endpoint SHALL include a `total` field in the response envelope alongside the `messages` array, indicating the total number of matching records.
6. THE SPA SHALL render the Message_List as a table with columns: sender name/email, subject, date, and read/unread indicator.
7. THE SPA SHALL display pagination controls that allow the user to navigate between pages.
8. WHEN the user navigates to a new page, THE SPA SHALL fetch the corresponding page from the API_Server and re-render the Message_List without a full page reload.

---

### Requirement 3: Search and Filter Messages

**User Story:** As a user, I want to search and filter messages, so that I can quickly find relevant emails.

#### Acceptance Criteria

1. THE `GET /api/messages` endpoint SHALL support a `q` query parameter; WHEN provided, THE API_Server SHALL return only Messages where the subject, sender email/name, or body contains the Search_Query (case-insensitive substring match).
2. THE `GET /api/messages` endpoint SHALL support a `label` query parameter; WHEN provided, THE API_Server SHALL return only Messages whose `labels` JSON array contains the Label_Filter string (exact match).
3. THE `GET /api/messages` endpoint SHALL support an `is_read` query parameter (`true` or `false`); WHEN provided, THE API_Server SHALL filter Messages by their `is_read` value.
4. THE `GET /api/messages` endpoint SHALL support an `is_outgoing` query parameter (`true` or `false`); WHEN provided, THE API_Server SHALL filter Messages by their `is_outgoing` value.
5. THE SPA SHALL render a search input field; WHEN the user types a Search_Query and submits, THE SPA SHALL fetch filtered results from the API_Server and re-render the Message_List.
6. THE SPA SHALL render a label filter dropdown populated with distinct labels fetched from the API_Server; WHEN the user selects a label, THE SPA SHALL re-fetch and re-render the Message_List.
7. WHEN any filter or search parameter changes, THE SPA SHALL reset the current page to `1` before fetching results.

---

### Requirement 4: View Message Detail

**User Story:** As a user, I want to click on a message and read its full content, so that I can view the email body and metadata.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `GET /api/messages/{message_id}` endpoint that returns the full Message record including the `body` field.
2. IF no Message with the given `message_id` exists, THEN THE API_Server SHALL return HTTP 404 with a JSON error body `{"error": "Message not found"}`.
3. WHEN the user clicks a row in the Message_List, THE SPA SHALL fetch the Message_Detail from `GET /api/messages/{message_id}` and render it in a detail panel or modal without a full page reload.
4. THE SPA SHALL display the following fields in the Message_Detail view: subject, sender name and email, recipient list (to, cc, bcc), date/time, labels, and body text.
5. THE SPA SHALL provide a way to close or dismiss the Message_Detail view and return focus to the Message_List.

---

### Requirement 5: List Available Labels

**User Story:** As a user, I want to see all available labels, so that I can filter my messages by label.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `GET /api/labels` endpoint that returns a JSON array of distinct label strings present across all non-deleted Messages, sorted alphabetically.
2. WHEN the SPA initialises, THE SPA SHALL fetch the label list from `GET /api/labels` and populate the label filter dropdown.

---

### Requirement 6: Handle Deleted Messages

**User Story:** As a user, I want deleted messages to be hidden by default, so that my view is not cluttered with removed emails.

#### Acceptance Criteria

1. THE `GET /api/messages` endpoint SHALL exclude Messages where `is_deleted` is `true` by default.
2. THE `GET /api/messages` endpoint SHALL support a `include_deleted` query parameter (`true`); WHEN provided, THE API_Server SHALL include deleted Messages in the results.
3. THE SPA SHALL visually distinguish deleted Messages (e.g., with a strikethrough or muted style) WHEN they are included in the Message_List.

---

### Requirement 7: Error Handling

**User Story:** As a user, I want clear feedback when something goes wrong, so that I understand the state of the application.

#### Acceptance Criteria

1. IF the API_Server returns an HTTP error response (4xx or 5xx), THEN THE SPA SHALL display a human-readable error message to the user within the main content area.
2. IF a database query fails, THEN THE API_Server SHALL return HTTP 500 with a JSON body `{"error": "<description>"}` and log the exception to stderr.
3. IF the `page` or `page_size` query parameters are not valid positive integers, THEN THE API_Server SHALL return HTTP 400 with a JSON body `{"error": "<description>"}`.
