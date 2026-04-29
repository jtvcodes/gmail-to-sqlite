# Implementation Plan: message-html-view

## Overview

Pure frontend change to `web/static/messageDetail.js` and `web/static/style.css`. Adds an `activeView` state variable, a `renderBody()` helper, a `buildToggleButton()` helper, and the corresponding CSS. No backend changes are required — the API already returns both `body` and `body_html` fields.

## Tasks

- [x] 1. Add `activeView` state and reset it on every `render()` call
  - Declare `let activeView = "html"` as a module-level variable at the top of `messageDetail.js`.
  - At the very start of `render()`, set `activeView = "html"` before any DOM work.
  - This ensures every newly opened message starts in HTML view and that re-opening a message resets the state.
  - _Requirements: 1.1, 1.4_

- [x] 2. Implement `renderBody()` helper and wire it into `render()`
  - [x] 2.1 Implement `renderBody(iframe, msg, view)` in `messageDetail.js`
    - When `view === "html"`: use `msg.body_html` if non-empty, otherwise fall back to `msg.body`.
    - When `view === "text"`: use `msg.body`, wrapped in `<pre>` with HTML-escaping and URL linkification (same logic as the existing plain-text branch).
    - Write the chosen content into the iframe via `doc.open()` / `doc.write()` / `doc.close()`, including the existing base `<style>` block.
    - After writing, trigger the iframe height resize (existing `load` listener + `setTimeout` fallback).
    - _Requirements: 1.2, 1.3, 2.4, 2.5, 2.6, 5.2_

  - [x] 2.2 Replace the existing inline iframe-writing block in `render()` with a call to `renderBody()`
    - Remove the old `isHtml` detection block and the direct `doc.open()` / `doc.write()` calls from `render()`.
    - Call `renderBody(iframe, msg, activeView)` in their place.
    - _Requirements: 1.2, 1.3_

  - [x] 2.3 Write property test for content selection (Property 2)
    - **Property 2: Content selection correctness**
    - For any message object and any `activeView` value, the content-selection logic SHALL pick `body_html` (or fall back to `body`) when view is `"html"`, and always pick `body` when view is `"text"`.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 1.2, 1.3, 2.4, 2.5**

  - [x] 2.4 Write property test for plain-text rendering (Property 6)
    - **Property 6: Plain-text view wraps body in `<pre>` with linkified URLs**
    - For any body string containing URL patterns, the rendered output SHALL wrap content in `<pre>` and replace URLs with `<a>` tags.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 2.6**

- [x] 3. Checkpoint — Ensure `renderBody()` works correctly
  - Ensure all existing tests still pass after the refactor.
  - Manually verify that opening a message still renders the body in the iframe.
  - Ask the user if any questions arise.

- [x] 4. Implement `buildToggleButton()` helper and wire it into `render()`
  - [x] 4.1 Implement `buildToggleButton(msg, iframe, bodyDiv)` in `messageDetail.js`
    - Compute `hasHtml = msg.body_html != null && msg.body_html !== ""` and `hasPlain = msg.body != null && msg.body !== ""`.
    - Return `null` if either `hasHtml` or `hasPlain` is false (toggle hidden when only one field is available).
    - Otherwise create a `<button>` element with:
      - CSS class `view-toggle-btn` always present.
      - CSS class `view-toggle-btn--active` added when `activeView === "text"`.
      - Label `"Plain text"` when `activeView === "html"`, `"HTML"` when `activeView === "text"`.
    - Attach a click handler that: flips `activeView`, calls `renderBody(iframe, msg, activeView)`, updates the button label and toggles `view-toggle-btn--active` in-place.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 4.3, 5.1_

  - [x] 4.2 Insert the toggle button into `render()` after the meta block and before the body section
    - Call `buildToggleButton(msg, iframe, bodyDiv)` after the labels block.
    - If the return value is non-null, append the button to the panel before `bodyDiv`.
    - Position satisfies requirement 4.1 (visible without scrolling, near the meta block).
    - _Requirements: 4.1, 3.1, 3.2, 3.3_

  - [x] 4.3 Write property test for toggle visibility (Property 4)
    - **Property 4: Toggle visibility iff both fields are non-empty**
    - For any message object, the toggle SHALL be present if and only if both `body_html` and `body` are non-empty strings.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 2.1, 3.1, 3.2, 3.3**

  - [x] 4.4 Write property test for toggle label (Property 3)
    - **Property 3: Toggle label is always the opposite view name**
    - For any `activeView` value, the button label SHALL be `"Plain text"` when `activeView === "html"` and `"HTML"` when `activeView === "text"`.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 2.2, 2.3**

  - [x] 4.5 Write property test for active CSS class (Property 7)
    - **Property 7: Active state class applied iff Plain_Text_View**
    - For any message with both fields non-empty, the button SHALL have `view-toggle-btn--active` if and only if `activeView === "text"`.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 4.3**

  - [x] 4.6 Write property test for toggle round-trip (Property 5)
    - **Property 5: Toggle is a round-trip**
    - For any message with both fields non-empty, toggling twice SHALL return `activeView` to its original value and produce the same content selection as before the first toggle.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 2.4, 2.5**

- [x] 5. Add CSS for `.view-toggle-btn` and `.view-toggle-btn--active` in `style.css`
  - Add `.view-toggle-btn` rule: `padding: 6px 14px`, `border: 1px solid #ccc`, `border-radius: 4px`, `background: #fff`, `cursor: pointer`, `font-size: 14px`, `color: #333`.
  - Add `.view-toggle-btn--active` rule: `background: #e8f0fe`, `border-color: #1a73e8`, `color: #1a73e8`.
  - _Requirements: 4.2, 4.3_

- [x] 6. Write unit and property tests for `activeView` reset and panel visibility
  - [x] 6.1 Write example-based unit tests in `web/tests/test_message_html_view.py`
    - Test content-selection helper for all 4 combinations of `body_html`/`body` nullability × 2 view states (8 cases).
    - Test toggle visibility for: both fields present, only `body`, only `body_html`, both absent.
    - _Requirements: 1.2, 1.3, 3.1, 3.2, 3.3_

  - [x] 6.2 Write property test for default view reset (Property 1)
    - **Property 1: Default view is always HTML**
    - For any message object, `activeView` after a `render()` call SHALL be `"html"`, regardless of the previous view state.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 1.1, 1.4**

  - [x] 6.3 Write property test for panel stays open after toggle (Property 8)
    - **Property 8: Panel remains open after toggle**
    - For any message with both fields non-empty, after the View_Toggle is activated the `#message-detail` panel SHALL remain visible.
    - Implement in `web/tests/test_message_html_view_properties.py` using Hypothesis.
    - **Validates: Requirements 5.1**

- [x] 7. Final checkpoint — Ensure all tests pass
  - Run `pytest web/tests/` and confirm all tests pass.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP.
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation.
- Property tests validate universal correctness properties using Hypothesis (already used in this project).
- Unit tests validate specific examples and edge cases.
- The pure helper functions (`renderBody` content-selection logic, toggle visibility logic, toggle label logic) should be tested by re-implementing the equivalent Python logic in the property test files, as the design recommends.
