# Missing DB UX Bugfix Design

## Overview

When the `messages` table does not exist in the connected SQLite database, both
`GET /api/messages` and `GET /api/messages/<id>` propagate the raw SQLite
exception `"no such table: messages"` as an HTTP 500 response. The frontend's
`_apiFetch` helper extracts the `error` field from the JSON body and throws it
verbatim, so the error banner displays the raw SQLite message with no guidance
for the user.

The fix intercepts this specific exception in `web/api/messages.py` — before
the generic `except` clause returns a 500 — and returns HTTP 503 with a
human-readable message. All other code paths (normal queries, 404s, 400s, other
SQLite errors) are left completely unchanged.

---

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a SQLite
  `OperationalError` whose message is exactly `"no such table: messages"` is
  raised while executing a query in `list_messages` or `get_message`.
- **Property (P)**: The desired behavior when the bug condition holds — the
  endpoint returns HTTP 503 with a friendly, actionable error body instead of
  HTTP 500 with the raw SQLite message.
- **Preservation**: All existing behavior for requests that do NOT trigger the
  bug condition must remain byte-for-byte identical after the fix.
- **`list_messages`**: The Flask view in `web/api/messages.py` that handles
  `GET /api/messages`. It executes a `COUNT(*)` and a `SELECT` against the
  `messages` table.
- **`get_message`**: The Flask view in `web/api/messages.py` that handles
  `GET /api/messages/<message_id>`. It executes a single `SELECT` against the
  `messages` table.
- **`_apiFetch`**: The JavaScript helper in `web/static/api.js` that reads
  `body.error` from non-2xx responses and throws it as an `Error`, causing
  `app.js` to display it in the `#error-banner` element.
- **`no_table_db`**: A test fixture that provides a SQLite database file that
  exists on disk but contains no tables — the canonical trigger for the bug.

---

## Bug Details

### Bug Condition

The bug manifests when either `list_messages` or `get_message` executes a SQL
statement against a database that has no `messages` table. SQLite raises
`sqlite3.OperationalError: no such table: messages`. The existing `except
Exception` handler in both views catches this and returns it verbatim as a 500
response. The frontend then displays the raw SQLite error string in the error
banner.

**Formal Specification:**

```
FUNCTION isBugCondition(exc)
  INPUT:  exc — an exception raised during DB query execution
  OUTPUT: boolean

  RETURN isinstance(exc, sqlite3.OperationalError)
         AND str(exc) == "no such table: messages"
END FUNCTION
```

### Examples

- **`GET /api/messages` on empty DB** — currently returns
  `HTTP 500 {"error": "no such table: messages"}`;
  expected: `HTTP 503 {"error": "Database not ready — please run the sync command to populate the database."}`

- **`GET /api/messages/abc123` on empty DB** — currently returns
  `HTTP 500 {"error": "no such table: messages"}`;
  expected: `HTTP 503 {"error": "Database not ready — please run the sync command to populate the database."}`

- **`GET /api/messages` on a populated DB** — currently returns HTTP 200 with
  paginated results; must continue to do so after the fix.

- **`GET /api/messages/does_not_exist` on a populated DB** — currently returns
  `HTTP 404 {"error": "Message not found"}`; must continue to do so after the fix.

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- `GET /api/messages` with a populated `messages` table SHALL continue to
  return HTTP 200 with the paginated message list envelope
  (`messages`, `total`, `page`, `page_size`).
- `GET /api/messages/<id>` with a valid `message_id` SHALL continue to return
  HTTP 200 with the full message detail object.
- `GET /api/messages/<id>` with an unknown `message_id` SHALL continue to
  return HTTP 404 with `{"error": "Message not found"}`.
- `GET /api/messages` with invalid query parameters (e.g. `page=0`) SHALL
  continue to return HTTP 400 with the existing validation error message.
- Any SQLite error that is NOT `"no such table: messages"` SHALL continue to
  return HTTP 500 with the original error message.

**Scope:**

All requests that do NOT trigger the bug condition (i.e. the `messages` table
exists, or a different exception is raised) must be completely unaffected by
this fix. This includes:

- All successful reads from a populated database
- All 404 responses for unknown message IDs
- All 400 responses for invalid query parameters
- All 500 responses for unrelated database errors

---

## Hypothesized Root Cause

Based on the bug description and code inspection, the root cause is:

1. **Missing specific-error check before the generic handler**: Both
   `list_messages` and `get_message` use a broad `except Exception as exc`
   clause that returns `str(exc)` as the error body with status 500. There is
   no prior check for the specific `sqlite3.OperationalError` with the message
   `"no such table: messages"`, so this case falls through to the generic
   handler and leaks the raw SQLite message.

2. **No table-existence guard at query time**: Neither view checks whether the
   `messages` table exists before executing queries. A pre-flight `SELECT name
   FROM sqlite_master WHERE type='table' AND name='messages'` would also work,
   but catching the exception is simpler and avoids an extra round-trip.

3. **Frontend passes error strings through unchanged**: `_apiFetch` in
   `api.js` reads `body.error` and throws it directly as `new Error(message)`.
   `app.js` then sets `state.error = err.message` and calls `renderError()`,
   which writes that string verbatim into `#error-banner`. There is no
   client-side mapping of 503 to a friendly message, so the fix must originate
   on the server side.

---

## Correctness Properties

Property 1: Bug Condition — Missing Table Returns 503 with Friendly Message

_For any_ request to `GET /api/messages` or `GET /api/messages/<id>` where the
`messages` table does not exist in the database (isBugCondition returns true),
the fixed endpoint SHALL return HTTP 503 with a JSON body whose `"error"` field
contains a human-readable message instructing the user to run the sync command,
and SHALL NOT return HTTP 500 or expose the raw SQLite error string.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — Normal Behavior Is Unchanged

_For any_ request where the bug condition does NOT hold (isBugCondition returns
false — i.e. the `messages` table exists, or a different exception is raised),
the fixed endpoints SHALL produce exactly the same HTTP status code, headers,
and response body as the original (unfixed) endpoints, preserving all existing
200, 404, 400, and 500 behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

---

## Fix Implementation

### Changes Required

**File**: `web/api/messages.py`

**Functions**: `list_messages`, `get_message`

**Specific Changes**:

1. **Add a `_is_missing_table_error` helper** (module-level): A small function
   that returns `True` when an exception is a `sqlite3.OperationalError` whose
   string representation is `"no such table: messages"`. Centralising the check
   avoids duplicating the string literal.

   ```python
   def _is_missing_table_error(exc: Exception) -> bool:
       return (
           isinstance(exc, sqlite3.OperationalError)
           and str(exc) == "no such table: messages"
       )
   ```

2. **Update `list_messages` exception handler**: Before the existing
   `return jsonify({"error": str(exc)}), 500` line, add:

   ```python
   if _is_missing_table_error(exc):
       return jsonify({
           "error": "Database not ready — please run the sync command to populate the database."
       }), 503
   ```

3. **Update `get_message` exception handler**: Apply the identical guard in the
   `except` block of `get_message`.

4. **No frontend changes required**: The existing `_apiFetch` → `state.error`
   → `renderError()` pipeline already displays whatever string is in
   `body.error`. Once the server returns the friendly message, the banner will
   show it automatically.

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface
counterexamples that demonstrate the bug on unfixed code, then verify the fix
works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing
the fix. Confirm or refute the root cause analysis. If we refute, we will need
to re-hypothesize.

**Test Plan**: Create a Flask test client backed by a database file that exists
on disk but has no tables (the `no_table_db` fixture). Issue requests to both
endpoints and assert that the response is NOT HTTP 500 with the raw SQLite
string. Run these tests on the UNFIXED code to observe failures and confirm the
root cause.

**Test Cases**:

1. **List messages on empty DB** — `GET /api/messages` against a no-table DB;
   assert status is not 500 and body does not contain `"no such table"` (will
   fail on unfixed code).
2. **Get message on empty DB** — `GET /api/messages/any_id` against a no-table
   DB; assert status is not 500 and body does not contain `"no such table"`
   (will fail on unfixed code).

**Expected Counterexamples**:

- Both endpoints return `HTTP 500 {"error": "no such table: messages"}` on
  unfixed code, confirming the root cause is the missing specific-error check
  in the `except Exception` handler.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed
endpoints return HTTP 503 with the friendly message.

**Pseudocode:**

```
FOR ALL request WHERE isBugCondition(db_exception_raised_by(request)) DO
  response := fixed_endpoint(request)
  ASSERT response.status_code == 503
  ASSERT "no such table" NOT IN response.json["error"]
  ASSERT "sync" IN response.json["error"].lower()
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the
fixed endpoints produce the same result as the original endpoints.

**Pseudocode:**

```
FOR ALL request WHERE NOT isBugCondition(db_exception_raised_by(request)) DO
  ASSERT original_endpoint(request) == fixed_endpoint(request)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation
checking because:

- It generates many varied request parameter combinations automatically.
- It catches edge cases (unusual `page`/`page_size` values, exotic query
  strings, random `message_id` values) that manual unit tests might miss.
- It provides strong guarantees that no normal request path is broken by the
  fix.

**Test Plan**: Observe behavior on UNFIXED code first for requests against a
populated database, then write property-based tests capturing that behavior.

**Test Cases**:

1. **200 preservation** — Verify that `GET /api/messages` against a populated
   DB continues to return HTTP 200 with the correct envelope fields.
2. **404 preservation** — Verify that `GET /api/messages/<unknown_id>` against
   a populated DB continues to return HTTP 404 with `{"error": "Message not
   found"}`.
3. **400 preservation** — Verify that `GET /api/messages?page=0` continues to
   return HTTP 400 with the existing validation error.
4. **500 preservation** — Verify that a non-table-missing `OperationalError`
   (e.g. a corrupted DB) still returns HTTP 500 with the original error string.

### Unit Tests

- Test `_is_missing_table_error` with a `sqlite3.OperationalError("no such
  table: messages")` → returns `True`.
- Test `_is_missing_table_error` with a `sqlite3.OperationalError("disk I/O
  error")` → returns `False`.
- Test `_is_missing_table_error` with a generic `ValueError` → returns `False`.
- Test `GET /api/messages` on a no-table DB → HTTP 503, friendly message.
- Test `GET /api/messages/<id>` on a no-table DB → HTTP 503, friendly message.
- Test that the friendly message does NOT contain `"no such table"`.
- Test that the friendly message contains guidance (e.g. the word `"sync"`).

### Property-Based Tests

- Generate random valid query-parameter combinations (`page`, `page_size`, `q`,
  `label`, `is_read`, `is_outgoing`, `include_deleted`) and verify that every
  request against a populated DB returns HTTP 200 with the correct envelope
  structure (preservation of the happy path).
- Generate random `message_id` strings not present in the DB and verify that
  every `GET /api/messages/<id>` returns HTTP 404 (preservation of the 404
  path).
- Generate random `message_id` strings for messages that DO exist and verify
  HTTP 200 with all required detail fields (preservation of the detail path).

### Integration Tests

- Start the full Flask app with a no-table DB and verify the error banner text
  in the rendered HTML contains the friendly message (end-to-end 503 flow).
- Start the full Flask app with a populated DB, load the page, and verify the
  message list renders correctly (end-to-end happy path preservation).
