# To Field Object Display Bugfix Design

## Overview

The web viewer's message detail panel calls `.join(", ")` directly on the `recipients.to`,
`recipients.cc`, and `recipients.bcc` arrays. Each element in those arrays is a
`{name, email}` object, so JavaScript coerces it to the string `"[object Object]"` instead
of a human-readable address. The fix is a small, targeted helper function —
`formatRecipient(r)` — that maps each object to `"Name <email>"` (or just `"email"` when
no name is present) before joining. No other rendering logic changes.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a recipient array element is
  an object with `name`/`email` properties rather than a plain string, causing `.join()` to
  produce `"[object Object]"`.
- **Property (P)**: The desired behavior when the bug condition holds — each recipient is
  rendered as `"Name <email@example.com>"` or `"email@example.com"`.
- **Preservation**: All rendering behavior that must remain unchanged by the fix — the From
  field, subject, date, labels, body, empty-field omission, and the Gmail link.
- **formatRecipient(r)**: The new helper function to be added in `web/static/messageDetail.js`
  that converts a single recipient object to a formatted address string.
- **recipients**: The `msg.recipients` object returned by the API, with optional `to`, `cc`,
  and `bcc` array properties, each element being `{name: string, email: string}`.

## Bug Details

### Bug Condition

The bug manifests when any of the `recipients.to`, `recipients.cc`, or `recipients.bcc`
arrays contains at least one element and that element is an object (not a string). The
`render()` function calls `.join(", ")` directly on the array without first mapping each
element to a string, so JavaScript's default `Object.prototype.toString` produces
`"[object Object]"` for every recipient.

**Formal Specification:**
```
FUNCTION isBugCondition(recipient)
  INPUT: recipient — a single element from recipients.to / .cc / .bcc
  OUTPUT: boolean

  RETURN typeof recipient === 'object'
         AND recipient !== null
         AND 'email' IN recipient
END FUNCTION
```

### Examples

- **TO with name**: `{name: "Alice Smith", email: "alice@example.com"}` → currently renders
  `"[object Object]"`, should render `"Alice Smith <alice@example.com>"`
- **TO without name**: `{name: "", email: "bob@example.com"}` → currently renders
  `"[object Object]"`, should render `"bob@example.com"`
- **CC with name**: `{name: "Carol", email: "carol@example.com"}` → currently renders
  `"[object Object]"`, should render `"Carol <carol@example.com>"`
- **BCC with name**: `{name: "Dave", email: "dave@example.com"}` → currently renders
  `"[object Object]"`, should render `"Dave <dave@example.com>"`
- **Multiple recipients**: `[{name:"A",email:"a@x.com"},{name:"",email:"b@x.com"}]` →
  currently renders `"[object Object], [object Object]"`, should render
  `"A <a@x.com>, b@x.com"`

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The From field MUST continue to render using `sender.name` and `sender.email` exactly as
  before (the existing inline template string is not touched).
- Empty recipient arrays (to/cc/bcc) MUST continue to produce no rendered line in the detail
  panel.
- Subject, date, labels, body (HTML and plain-text), and the Gmail link MUST render
  identically to the current implementation.
- The iframe sandbox and auto-resize logic MUST remain unchanged.

**Scope:**
All inputs where no recipient array element satisfies `isBugCondition` — including messages
with no recipients, messages whose recipient fields are already plain strings (defensive
case), and all non-recipient parts of the detail panel — must be completely unaffected by
this fix.

## Hypothesized Root Cause

Based on the bug description and the source code in `web/static/messageDetail.js`:

1. **Direct `.join()` on object array**: Lines 43, 49, and 55 call
   `recipients.to.join(", ")`, `recipients.cc.join(", ")`, and `recipients.bcc.join(", ")`
   respectively. JavaScript's `Array.prototype.join` calls `.toString()` on each element;
   for plain objects this returns `"[object Object]"`. No mapping step exists.

2. **No `formatRecipient` helper**: There is no utility function that converts a
   `{name, email}` object to a display string. The From field uses an inline template
   string (`sender.name + " <" + sender.email + ">"`) but this pattern was never applied
   to the recipient arrays.

3. **API returns structured objects**: The API correctly returns recipients as
   `{name, email}` objects (consistent with how `sender` is structured). The bug is
   entirely in the rendering layer, not in the data layer.

## Correctness Properties

Property 1: Bug Condition - Recipient Objects Render as Formatted Addresses

_For any_ recipient element where `isBugCondition(recipient)` returns true (i.e., the
element is a `{name, email}` object), the fixed `render()` function SHALL display that
recipient as `"Name <email>"` when `name` is a non-empty string, or as `"email"` when
`name` is absent or empty — never as `"[object Object]"`.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Recipient Rendering Unchanged

_For any_ message where `isBugCondition` does NOT hold for any recipient element (empty
arrays, no recipients, or already-string elements), the fixed `render()` function SHALL
produce exactly the same DOM output as the original function, preserving the From field,
subject, date, labels, body, Gmail link, and empty-field omission behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

**File**: `web/static/messageDetail.js`

**Specific Changes**:

1. **Add `formatRecipient` helper** (before the `render` function):
   ```javascript
   function formatRecipient(r) {
     if (r && typeof r === 'object') {
       return r.name ? r.name + ' <' + r.email + '>' : (r.email || '');
     }
     // Defensive: already a string (future-proofing)
     return String(r);
   }
   ```

2. **Fix TO rendering** (replace line ~43):
   ```javascript
   // Before:
   toLine.textContent = "To: " + recipients.to.join(", ");
   // After:
   toLine.textContent = "To: " + recipients.to.map(formatRecipient).join(", ");
   ```

3. **Fix CC rendering** (replace line ~49):
   ```javascript
   // Before:
   ccLine.textContent = "Cc: " + recipients.cc.join(", ");
   // After:
   ccLine.textContent = "Cc: " + recipients.cc.map(formatRecipient).join(", ");
   ```

4. **Fix BCC rendering** (replace line ~55):
   ```javascript
   // Before:
   bccLine.textContent = "Bcc: " + recipients.bcc.join(", ");
   // After:
   bccLine.textContent = "Bcc: " + recipients.bcc.map(formatRecipient).join(", ");
   ```

No other files require changes. The API layer, database schema, and all other frontend
modules are unaffected.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that
demonstrate the bug on unfixed code, then verify the fix works correctly and preserves
existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix.
Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write unit tests for `formatRecipient` and for the rendered output of
`render()` given messages with `{name, email}` recipient objects. Run these tests on the
UNFIXED code to observe that `.join()` produces `"[object Object]"` and confirm the root
cause.

**Test Cases**:
1. **TO with name and email** (will fail on unfixed code): Pass
   `{name: "Alice", email: "alice@example.com"}` as a TO recipient; assert the rendered
   text contains `"Alice <alice@example.com>"` and does NOT contain `"[object Object]"`.
2. **TO with email only** (will fail on unfixed code): Pass
   `{name: "", email: "bob@example.com"}` as a TO recipient; assert the rendered text
   contains `"bob@example.com"` and does NOT contain `"[object Object]"`.
3. **CC with name and email** (will fail on unfixed code): Same pattern for CC field.
4. **BCC with name and email** (will fail on unfixed code): Same pattern for BCC field.
5. **Multiple TO recipients** (will fail on unfixed code): Pass two recipient objects;
   assert both are formatted and joined with `", "`.

**Expected Counterexamples**:
- Rendered text contains `"[object Object]"` instead of formatted addresses.
- Confirms root cause: `.join()` is called without a prior `.map(formatRecipient)` step.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function
produces the expected behavior.

**Pseudocode:**
```
FOR ALL recipient WHERE isBugCondition(recipient) DO
  result := formatRecipient(recipient)
  IF recipient.name IS non-empty THEN
    ASSERT result = recipient.name + " <" + recipient.email + ">"
  ELSE
    ASSERT result = recipient.email
  END IF
  ASSERT result does NOT contain "[object Object]"
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed
`render()` function produces the same DOM output as the original.

**Pseudocode:**
```
FOR ALL message WHERE NOT isBugCondition(any recipient in message) DO
  ASSERT render_original(message) = render_fixed(message)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking
because:
- It generates many recipient configurations automatically (empty arrays, varied names/emails).
- It catches edge cases that manual unit tests might miss (null name, empty email, etc.).
- It provides strong guarantees that non-recipient rendering is unchanged across all inputs.

**Test Plan**: Observe behavior on UNFIXED code first for messages with no recipients and
for the From/subject/date/labels/body fields, then write property-based tests capturing
that behavior.

**Test Cases**:
1. **Empty recipients preservation**: Messages with `{to:[], cc:[], bcc:[]}` must render
   no TO/CC/BCC lines — identical before and after the fix.
2. **From field preservation**: The From line must render `"From: Name <email>"` using the
   existing inline template, unaffected by the new helper.
3. **Subject/date/labels/body preservation**: All other detail-panel fields must render
   identically before and after the fix.
4. **`formatRecipient` with already-string input**: The defensive `String(r)` branch must
   return the input unchanged (future-proofing, no regression).

### Unit Tests

- Test `formatRecipient` with `{name, email}` → `"Name <email>"`.
- Test `formatRecipient` with `{name: "", email}` → `"email"`.
- Test `formatRecipient` with `{name: null, email}` → `"email"`.
- Test `formatRecipient` with a plain string (defensive branch) → same string.
- Test `render()` TO line with one recipient object → correct formatted string.
- Test `render()` CC and BCC lines with recipient objects → correct formatted strings.
- Test `render()` with empty TO/CC/BCC arrays → those lines are omitted.

### Property-Based Tests

- Generate random `{name, email}` objects and verify `formatRecipient` never returns
  `"[object Object]"` and always contains the email address.
- Generate random arrays of `{name, email}` objects and verify the joined TO/CC/BCC text
  matches the expected format for every element.
- Generate random messages with empty recipient arrays and verify the rendered panel
  contains no TO/CC/BCC lines (preservation of omission behavior).

### Integration Tests

- Open a seeded message with TO, CC, and BCC recipients in the full web viewer and verify
  all three fields display formatted addresses.
- Verify the From field, subject, date, labels, and body are unaffected after the fix is
  applied.
- Verify that a message with no CC or BCC recipients still omits those lines.
