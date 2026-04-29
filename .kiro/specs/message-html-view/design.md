# Design Document: message-html-view

## Overview

The Gmail Web Viewer currently uses a single `body` field and auto-detects whether content is HTML or plain text. The backend already stores and serves two distinct fields — `body_html` and `body` — via the `/api/messages/<message_id>` endpoint. This feature updates `messageDetail.js` to use `body_html` as the default rendering format and adds a View_Toggle button that lets the user switch to the plain-text view. The toggle state persists for the lifetime of the open panel and resets to HTML when a new message is opened.

The change is entirely frontend: no backend modifications are required. The API already returns both `body` and `body_html` in the detail response.

## Architecture

The feature is a self-contained modification to `web/static/messageDetail.js`. The component already owns the full render lifecycle for the detail panel, so the new state and toggle logic fit naturally inside it.

```
┌─────────────────────────────────────────────────────────┐
│  messageDetail.js                                        │
│                                                          │
│  state.selectedMessage  ──►  render()                    │
│                               │                          │
│                               ├─ activeView (HTML|TEXT)  │
│                               │                          │
│                               ├─ renderBody()            │
│                               │    ├─ HTML_View          │
│                               │    │   body_html → iframe│
│                               │    └─ Plain_Text_View    │
│                               │        body → iframe     │
│                               │                          │
│                               └─ View_Toggle button      │
│                                    (visible when both    │
│                                     fields non-empty)    │
└─────────────────────────────────────────────────────────┘
```

The `activeView` variable is module-level (or closure-scoped) within `messageDetail.js`, reset to `"html"` each time `render()` is called for a new message.

## Components and Interfaces

### `messageDetail.js` — updated module

**State added:**
- `activeView`: `"html" | "text"` — tracks the current rendering mode. Initialized to `"html"` on every `render()` call.

**Functions modified:**

`render()`
- Sets `activeView = "html"` at the start of every call (handles requirement 1.1 and 1.4).
- Calls `renderBody(iframe, msg, activeView)` to write iframe content.
- Conditionally creates and appends the View_Toggle button (requirement 3.1–3.3).

**Functions added:**

`renderBody(iframe, msg, view)`
- Determines which content to write into the iframe based on `view`:
  - `"html"`: uses `msg.body_html` if non-empty, falls back to `msg.body` (requirement 1.2–1.3).
  - `"text"`: uses `msg.body`, rendered as `<pre>` with URL linkification (requirement 2.6).
- Writes the content to `iframe.contentDocument` and triggers height resize.

`buildToggleButton(msg, bodyDiv)`
- Returns `null` if either `msg.body_html` or `msg.body` is empty/null (requirement 3.2–3.3).
- Otherwise creates a `<button>` element with:
  - Label `"Plain text"` when `activeView === "html"`, `"HTML"` when `activeView === "text"` (requirement 2.2–2.3).
  - CSS class `view-toggle-btn` always; adds `view-toggle-btn--active` when `activeView === "text"` (requirement 4.3).
  - Click handler that flips `activeView` and calls `renderBody()` + updates button label/class in-place (requirement 5.1).

### `style.css` — additions

New CSS rules for `.view-toggle-btn` and `.view-toggle-btn--active`:
- Base style matches existing secondary action buttons (`border: 1px solid #ccc`, `border-radius: 4px`, `background: #fff`, `font-size: 14px`, `padding: 6px 14px`).
- Active state (`.view-toggle-btn--active`): `background: #e8f0fe`, `border-color: #1a73e8`, `color: #1a73e8` to indicate non-default mode.

### API (no changes)

`GET /api/messages/<message_id>` already returns:
```json
{
  "body": "plain text content",
  "body_html": "<html>...</html> or null"
}
```
No backend changes are needed.

## Data Models

### View state

```javascript
// Module-level variable in messageDetail.js
let activeView = "html"; // "html" | "text"
```

### Message object (existing, relevant fields)

```javascript
{
  body: string | null,       // plain-text body
  body_html: string | null,  // HTML body
  // ... other fields unchanged
}
```

### Toggle visibility logic

```
hasHtml  = msg.body_html != null && msg.body_html !== ""
hasPlain = msg.body      != null && msg.body      !== ""

showToggle = hasHtml && hasPlain
```

### Content selection logic

```
if activeView === "html":
    content = hasHtml ? msg.body_html : msg.body
else:
    content = msg.body  (rendered as <pre> with linkification)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

The rendering logic in `messageDetail.js` is pure DOM manipulation driven by a message object and a view-state string. The content-selection and toggle-visibility functions are pure functions of their inputs, making them well-suited for property-based testing.

### Property 1: Default view is always HTML

*For any* message object passed to `render()`, the `activeView` after rendering SHALL be `"html"`, regardless of the previous view state.

**Validates: Requirements 1.1, 1.4**

---

### Property 2: Content selection correctness

*For any* message object and any `activeView` value, `renderBody` SHALL select content according to the rule: when `activeView` is `"html"`, use `body_html` if non-empty, otherwise fall back to `body`; when `activeView` is `"text"`, always use `body`.

**Validates: Requirements 1.2, 1.3, 2.4, 2.5**

---

### Property 3: Toggle label is always the opposite view name

*For any* `activeView` state, the View_Toggle button label SHALL be `"Plain text"` when `activeView` is `"html"`, and `"HTML"` when `activeView` is `"text"`.

**Validates: Requirements 2.2, 2.3**

---

### Property 4: Toggle visibility iff both fields are non-empty

*For any* message object, the View_Toggle button SHALL be present in the rendered panel if and only if both `body_html` and `body` are non-empty strings.

**Validates: Requirements 2.1, 3.1, 3.2, 3.3**

---

### Property 5: Toggle is a round-trip

*For any* message with both `body_html` and `body` non-empty, toggling the View_Toggle twice SHALL return `activeView` to its original value and render the same content as before the first toggle.

**Validates: Requirements 2.4, 2.5**

---

### Property 6: Plain-text view wraps body in pre with linkified URLs

*For any* message in `"text"` view, the iframe content SHALL wrap the `body` field in a `<pre>` element, and any URL patterns in `body` SHALL be replaced with anchor tags.

**Validates: Requirements 2.6**

---

### Property 7: Active state class applied iff Plain_Text_View

*For any* message with both fields non-empty, the View_Toggle button SHALL have the `view-toggle-btn--active` CSS class if and only if `activeView` is `"text"`.

**Validates: Requirements 4.3**

---

### Property 8: Panel remains open after toggle

*For any* message, after the user activates the View_Toggle, the `#message-detail` panel SHALL remain visible (not hidden).

**Validates: Requirements 5.1**

## Error Handling

**`body_html` is null or empty string:**
- Fall back to `body` for HTML_View rendering (requirement 1.3).
- Hide the View_Toggle (requirement 3.2).
- No error is shown to the user; the message still renders.

**`body` is null or empty string:**
- Hide the View_Toggle (requirement 3.3).
- Render `body_html` directly without offering a plain-text alternative.

**Both `body` and `body_html` are null/empty:**
- Render an empty iframe (existing behavior for messages with no body).
- No toggle is shown.

**iframe `contentDocument` unavailable:**
- The existing fallback `setTimeout` resize guard already handles this case.
- No new error handling needed.

## Testing Strategy

### Unit / example-based tests

Located in `web/tests/test_message_html_view.py` (new file).

Focus areas:
- Verify `GET /api/messages/<id>` returns both `body` and `body_html` fields (already covered by existing `TestBodyHtml` tests in `test_web_messages.py`; no duplication needed).
- Verify the content-selection helper returns the correct field for each combination of `activeView`, `body_html`, and `body` values (4 combinations × 2 view states = 8 example tests).
- Verify toggle visibility for the three cases: both present, only `body`, only `body_html`.

### Property-based tests

Located in `web/tests/test_message_html_view_properties.py` (new file).

Uses [Hypothesis](https://hypothesis.readthedocs.io/) (already used in this project).

Each property test runs a minimum of **100 iterations**.

Tag format: `# Feature: message-html-view, Property N: <property_text>`

| Test | Property | Hypothesis strategy |
|------|----------|---------------------|
| `test_property_1_default_view_is_html` | Property 1 | Random message objects |
| `test_property_2_content_selection` | Property 2 | Random messages × `activeView` values |
| `test_property_3_toggle_label` | Property 3 | `st.sampled_from(["html", "text"])` |
| `test_property_4_toggle_visibility` | Property 4 | Random messages with varying body/body_html nullability |
| `test_property_5_toggle_round_trip` | Property 5 | Random messages with both fields non-empty |
| `test_property_6_plain_text_rendering` | Property 6 | Random body strings including URLs |
| `test_property_7_active_class` | Property 7 | Random messages × `activeView` values |
| `test_property_8_panel_stays_open` | Property 8 | Random messages with both fields non-empty |

Because `messageDetail.js` is a browser-side module, the property tests will target the **pure helper functions** extracted from it (content selection, toggle label, toggle visibility, plain-text rendering). These functions have no DOM or browser dependencies and can be tested directly in Python by re-implementing the same logic, or by extracting them into a testable module. The recommended approach is to extract the pure logic into a small `messageDetailHelpers.js` module and test the equivalent Python logic in the property tests, keeping the DOM wiring in `messageDetail.js`.

### Integration / visual tests

- Manual verification that the toggle button appears in the correct position (near the subject/meta block) and uses consistent styling.
- Manual verification that toggling updates the iframe content without closing the panel.
- Manual verification that scroll position is preserved at the top of the body section after toggle.
