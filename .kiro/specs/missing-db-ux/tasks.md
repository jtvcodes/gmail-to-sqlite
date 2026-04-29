# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Missing Table Returns 500 with Raw SQLite Error
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to the two concrete failing cases: `GET /api/messages` and `GET /api/messages/<id>` against a no-table database
  - Create a `no_table_db` fixture: a SQLite file that exists on disk but contains no tables (do NOT run `CREATE TABLE`)
  - Test that `GET /api/messages` on a no-table DB does NOT return HTTP 500 with `"no such table"` in the error body (from Bug Condition in design: `isBugCondition(exc)` where `isinstance(exc, sqlite3.OperationalError) AND str(exc) == "no such table: messages"`)
  - Test that `GET /api/messages/any_id` on a no-table DB does NOT return HTTP 500 with `"no such table"` in the error body
  - The assertions should match the Expected Behavior: status 503, friendly message containing `"sync"`, no raw SQLite string
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists)
  - Document counterexamples found (e.g. `GET /api/messages` returns `HTTP 500 {"error": "no such table: messages"}`)
  - Mark task complete when tests are written, run, and failure is documented
  - _Requirements: 1.1, 1.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Normal Behavior Is Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code (populated DB): `GET /api/messages` returns HTTP 200 with envelope `{messages, total, page, page_size}`
  - Observe on UNFIXED code: `GET /api/messages/<unknown_id>` returns `HTTP 404 {"error": "Message not found"}`
  - Observe on UNFIXED code: `GET /api/messages?page=0` returns HTTP 400 with an `"error"` field
  - Observe on UNFIXED code: a non-table-missing `OperationalError` returns HTTP 500 with the original error string
  - Write property-based tests in `web/tests/` capturing these observed behaviors (from Preservation Requirements in design):
    - For all valid query-parameter combinations against a populated DB → HTTP 200 with correct envelope structure
    - For all unknown `message_id` values against a populated DB → HTTP 404 with `{"error": "Message not found"}`
    - For all invalid `page`/`page_size` values → HTTP 400 with an `"error"` field
    - For a non-table-missing `OperationalError` → HTTP 500 with the original error string (not 503)
  - Verify all preservation tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for missing-table UX — return HTTP 503 with friendly message

  - [x] 3.1 Implement the fix in `web/api/messages.py`
    - Add a module-level helper `_is_missing_table_error(exc)` that returns `True` when `isinstance(exc, sqlite3.OperationalError) and str(exc) == "no such table: messages"`
    - In `list_messages` exception handler: before the existing `return jsonify({"error": str(exc)}), 500`, add a guard that calls `_is_missing_table_error(exc)` and returns `jsonify({"error": "Database not ready — please run the sync command to populate the database."}), 503`
    - Apply the identical guard in the `except` block of `get_message`
    - No frontend changes required — `_apiFetch` → `state.error` → `renderError()` already displays whatever string is in `body.error`
    - _Bug_Condition: `isBugCondition(exc)` where `isinstance(exc, sqlite3.OperationalError) AND str(exc) == "no such table: messages"`_
    - _Expected_Behavior: HTTP 503 with `{"error": "Database not ready — please run the sync command to populate the database."}`; no HTTP 500; no raw SQLite string in response_
    - _Preservation: All 200/404/400/500 paths for requests where the messages table exists or a different exception is raised must remain byte-for-byte identical_
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Missing Table Returns 503 with Friendly Message
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior (HTTP 503, friendly message, no raw SQLite string)
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Normal Behavior Is Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run all preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all 200/404/400/500 paths are unaffected by the fix
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the full test suite (`pytest web/tests/`) and confirm all tests pass
  - Ensure all tests pass; ask the user if questions arise
