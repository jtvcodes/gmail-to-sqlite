# Bugfix Requirements Document

## Introduction

When the `messages` table does not exist in the connected SQLite database (e.g. the database file is empty, newly created, or was never populated by the sync command), every API endpoint that queries the `messages` table raises a raw SQLite exception. That exception message — `"no such table: messages"` — is forwarded verbatim to the frontend and displayed in the error banner, giving users no actionable guidance. The fix should intercept this specific failure condition at the API layer and return a clear, user-friendly error response, while leaving all normal (table-present) behavior unchanged.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the `messages` table does not exist in the database AND a request is made to `GET /api/messages` THEN the system returns HTTP 500 with the raw error body `{"error": "no such table: messages"}`

1.2 WHEN the `messages` table does not exist in the database AND a request is made to `GET /api/messages/<id>` THEN the system returns HTTP 500 with the raw error body `{"error": "no such table: messages"}`

1.3 WHEN the raw `"no such table: messages"` error string is received by the frontend THEN the system displays it verbatim in the error banner, giving the user no guidance on how to resolve the problem

### Expected Behavior (Correct)

2.1 WHEN the `messages` table does not exist in the database AND a request is made to `GET /api/messages` THEN the system SHALL return HTTP 503 with a friendly error body such as `{"error": "Database not ready — please run the sync command to populate the database."}`

2.2 WHEN the `messages` table does not exist in the database AND a request is made to `GET /api/messages/<id>` THEN the system SHALL return HTTP 503 with a friendly error body such as `{"error": "Database not ready — please run the sync command to populate the database."}`

2.3 WHEN the frontend receives a 503 response with a friendly error message THEN the system SHALL display that message in the error banner so the user understands what action to take

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the `messages` table exists and contains rows AND a request is made to `GET /api/messages` THEN the system SHALL CONTINUE TO return HTTP 200 with the paginated message list

3.2 WHEN the `messages` table exists and a valid `message_id` is requested via `GET /api/messages/<id>` THEN the system SHALL CONTINUE TO return HTTP 200 with the message detail

3.3 WHEN the `messages` table exists and an unknown `message_id` is requested via `GET /api/messages/<id>` THEN the system SHALL CONTINUE TO return HTTP 404 with `{"error": "Message not found"}`

3.4 WHEN a request to `GET /api/messages` includes invalid query parameters (e.g. non-integer `page`) THEN the system SHALL CONTINUE TO return HTTP 400 with the existing validation error message

3.5 WHEN a different, unrelated SQLite error occurs (not `"no such table: messages"`) THEN the system SHALL CONTINUE TO return HTTP 500 with the original error message
