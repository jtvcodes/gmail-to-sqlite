# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Recipient Objects Render as [object Object]
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases — recipient objects with an `email` property (where `isBugCondition(r)` returns true)
  - Add a test file `web/tests/test_recipient_formatting.py` (or equivalent JS test)
  - Test that `formatRecipient({name: "Alice", email: "alice@example.com"})` returns `"Alice <alice@example.com>"` and NOT `"[object Object]"`
  - Test that `formatRecipient({name: "", email: "bob@example.com"})` returns `"bob@example.com"` and NOT `"[object Object]"`
  - Test that the rendered TO line for a message with `recipients.to = [{name:"Alice", email:"alice@example.com"}]` contains `"Alice <alice@example.com>"` and does NOT contain `"[object Object]"`
  - Test CC and BCC fields with the same pattern
  - Test multiple recipients: `[{name:"A",email:"a@x.com"},{name:"",email:"b@x.com"}]` → `"A <a@x.com>, b@x.com"`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists; `.join()` produces `"[object Object]"`)
  - Document counterexamples found (e.g., `recipients.to.join(", ")` on `[{name:"Alice",email:"alice@example.com"}]` yields `"[object Object]"`)
  - Mark task complete when tests are written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Recipient Rendering Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for messages where `isBugCondition` does NOT hold for any recipient (empty arrays, no recipients)
  - Observe: a message with `{to:[], cc:[], bcc:[]}` renders no TO/CC/BCC lines on unfixed code
  - Observe: the From line renders `"From: Name <email>"` using the existing inline template, unaffected by recipient arrays
  - Observe: subject, date, labels, body, and Gmail link render correctly on unfixed code
  - Write property-based tests (using Hypothesis or equivalent) capturing these observed behaviors:
    - For all messages with empty `to`/`cc`/`bcc` arrays, no TO/CC/BCC line appears in the rendered output
    - For all messages, the From field renders using `sender.name` and `sender.email` exactly as before
    - For all messages, subject, date, labels, body, and Gmail link are unaffected
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix recipient rendering in messageDetail.js

  - [x] 3.1 Add `formatRecipient` helper function to `web/static/messageDetail.js`
    - Insert before the `render` function:
      ```javascript
      function formatRecipient(r) {
        if (r && typeof r === 'object') {
          return r.name ? r.name + ' <' + r.email + '>' : (r.email || '');
        }
        return String(r);
      }
      ```
    - _Bug_Condition: `isBugCondition(r)` where `typeof r === 'object' && r !== null && 'email' in r`_
    - _Expected_Behavior: `r.name ? r.name + " <" + r.email + ">" : (r.email || "")` — never `"[object Object]"`_
    - _Preservation: defensive `String(r)` branch handles already-string inputs unchanged_
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.2 Replace `.join(", ")` with `.map(formatRecipient).join(", ")` for TO, CC, and BCC
    - Replace `recipients.to.join(", ")` → `recipients.to.map(formatRecipient).join(", ")`
    - Replace `recipients.cc.join(", ")` → `recipients.cc.map(formatRecipient).join(", ")`
    - Replace `recipients.bcc.join(", ")` → `recipients.bcc.map(formatRecipient).join(", ")`
    - No other lines in `render()` are changed
    - _Bug_Condition: direct `.join()` on `{name, email}` object arrays produces `"[object Object]"`_
    - _Preservation: empty-array guard (`length > 0`) and all other rendering logic remain untouched_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Recipient Objects Render as Formatted Addresses
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms bug is fixed — formatted addresses appear, no `"[object Object]"`)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Recipient Rendering Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — From field, subject, date, labels, body, empty-field omission all unchanged)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the full test suite (`pytest` and any JS tests)
  - Ensure all tests pass; ask the user if questions arise
