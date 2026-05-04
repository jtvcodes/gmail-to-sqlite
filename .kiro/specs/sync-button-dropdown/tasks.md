# Implementation Plan: Sync Button Dropdown

## Overview

Replace the single `⟳ Sync` button with a split button control. The primary segment triggers a delta sync; a chevron toggle opens a dropdown with all three sync modes. The backend `/api/sync` endpoint is extended to accept a `mode` parameter and route to the correct `main.py` subprocess flags.

## Tasks

- [x] 1. Extend backend sync endpoint to accept mode parameter
  - In `web/api/sync.py`, read the optional `mode` field from the JSON request body using `request.get_json(silent=True, force=True)`
  - Build the subprocess command based on mode: `delta` → `--delta`, `force` → `--force`, `missing`/absent → no extra flag
  - Return HTTP 400 with a descriptive error message for any unrecognised mode value
  - Preserve all existing timeout (300 s), error-handling, and output-capture behaviour for every mode
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 1.1 Write property test for backend mode routing (Property 2)
    - **Property 2: Backend mode routing correctness**
    - Use Hypothesis `sampled_from(['delta', 'force', 'missing'])` for mode and `text()` for data_dir
    - Assert subprocess command contains exactly the expected flags for each mode (delta → `--delta` present, `--force` absent; force → `--force` present, `--delta` absent; missing → neither flag present)
    - **Validates: Requirements 3.3, 4.2, 5.2, 6.2, 6.3, 6.4**

  - [x] 1.2 Write property test for invalid mode rejection (Property 3)
    - **Property 3: Invalid mode values are rejected**
    - Use Hypothesis `text()` filtered to exclude `{'delta', 'force', 'missing'}`
    - Assert response status is 400 and the `error` field in the JSON body is non-empty
    - **Validates: Requirements 6.1, 6.5**

- [x] 2. Checkpoint — ensure backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Replace sync button HTML with split button structure
  - In `web/static/index.html`, remove `<button id="sync-btn" onclick="runSync()" disabled>⟳ Sync</button>`
  - Add the `.sync-split-btn` wrapper `<div>` containing `#sync-primary-btn`, `#sync-toggle-btn`, and `#sync-dropdown` `<ul>` as specified in the design
  - Set `aria-haspopup="true"`, `aria-expanded="false"`, and `aria-label="More sync options"` on the toggle button
  - Set `role="menu"` on the `<ul>` and `role="menuitem"` with `tabindex="-1"` on each `<li>`
  - Wire `onclick="runSync('delta')"` on the primary button and each "Sync New Data" menu item; `onclick="runSync('force')"` and `onclick="runSync('missing')"` on the other items
  - Wire `onclick="toggleSyncDropdown(event)"` on the toggle button
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 8.6, 8.7_

- [x] 4. Add split button and dropdown styles
  - In `web/static/style.css`, remove or replace the `#sync-btn` rule block
  - Add `.sync-split-btn`: `display: inline-flex`, no gap, `border-radius: 4px` on outer corners only
  - Add `.sync-primary`: left segment with rounded left corners and normal padding
  - Add `.sync-toggle`: right segment, narrow (~28 px), rounded right corners, left border separator
  - Add `.sync-dropdown-menu`: absolutely positioned below the toggle, `z-index: 150`, white background, border, shadow, `list-style: none`, `padding: 0`, `margin: 0`
  - Add `.sync-dropdown-menu li`: hover highlight, `cursor: pointer`, padding
  - Add disabled state: both segments get `opacity: 0.6; cursor: default` when `disabled`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 5. Update app.js — runSync, setLoading, and dropdown logic
  - [x] 5.1 Rewrite `runSync(mode)` to accept a mode parameter
    - Accept `mode` string (`'delta'`, `'force'`, `'missing'`)
    - Call `setLoading(true, labelForMode(mode))` where `labelForMode` maps modes to overlay strings: `delta` → `"Syncing new messages…"`, `force` → `"Force-syncing all messages…"`, `missing` → `"Syncing missing messages…"`
    - POST `{ mode }` as JSON to `/api/sync` with `Content-Type: application/json`
    - On success: call `loadLabels()` then `loadMessages()`; on error: set `state.error` and call `renderError()`
    - Always call `setLoading(false)` in `finally`
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 4.1, 4.3, 4.4, 5.1, 5.3, 5.4, 7.1, 7.2, 7.3_

  - [x] 5.2 Update `setLoading(on, label)` to target split button segments
    - Replace references to `#sync-btn` with `#sync-primary-btn` and `#sync-toggle-btn`
    - `on=true`: disable both segments; set primary button text to `"⟳ Syncing…"`
    - `on=false`: re-enable both segments; restore primary button text to `"⟳ Sync New Data"`
    - _Requirements: 1.4, 1.5, 1.6_

  - [x] 5.3 Implement `toggleSyncDropdown(event)` and `closeSyncDropdown()`
    - `toggleSyncDropdown`: if loading is in progress, do nothing; otherwise toggle `hidden` on `#sync-dropdown` and update `aria-expanded` on `#sync-toggle-btn`; register/remove a one-shot `document` click listener to close the menu when clicking outside
    - `closeSyncDropdown`: set `hidden` on `#sync-dropdown` and set `aria-expanded="false"` on `#sync-toggle-btn`
    - _Requirements: 2.5, 2.6, 8.2, 8.6_

  - [x] 5.4 Add keyboard navigation listener on `#sync-dropdown`
    - `ArrowDown` / `ArrowUp`: move focus between `[role="menuitem"]` elements (wrap around)
    - `Escape`: call `closeSyncDropdown()` and return focus to `#sync-toggle-btn`
    - `Enter` / `Space` on a focused item: trigger the item's `onclick` and close the dropdown
    - _Requirements: 8.3, 8.4, 8.5_

  - [x] 5.5 Write property test for loading round-trip (Property 1)
    - **Property 1: Loading state is a round-trip for split button segments**
    - Use fast-check to generate arbitrary initial label text for the primary button
    - Assert `setLoading(true)` then `setLoading(false)` restores `disabled=false` and the original label on both segments
    - **Validates: Requirements 1.6**

  - [x] 5.6 Write property test for loading overlay label (Property 5)
    - **Property 5: Loading overlay label matches sync mode**
    - Use fast-check `fc.constantFrom('delta', 'force', 'missing')` for mode
    - Assert the label string passed to `setLoading` matches the expected mode-specific string
    - **Validates: Requirements 7.1, 7.2, 7.3**

  - [x] 5.7 Write property test for error message surfacing (Property 4)
    - **Property 4: Error messages are surfaced to the UI**
    - Use fast-check to generate arbitrary non-empty error strings
    - Mock fetch to return a failed response containing that error string; assert `state.error` equals the string and the error banner displays it
    - **Validates: Requirements 3.5, 4.4, 5.4**

  - [x] 5.8 Write property test for aria-expanded accuracy (Property 6)
    - **Property 6: aria-expanded accurately reflects dropdown state**
    - Use fast-check to generate arbitrary sequences of open/close toggle operations
    - Assert after each operation that `aria-expanded` equals `"true"` iff `#sync-dropdown` does not have the `hidden` attribute
    - **Validates: Requirements 8.6**

  - [x] 5.9 Write property test for keyboard Enter triggering correct mode (Property 7)
    - **Property 7: Keyboard Enter on any menu item triggers its sync mode**
    - Use fast-check `fc.integer({min: 0, max: 2})` for item index
    - Assert pressing Enter on the item at that index calls `runSync` with the correct mode (`delta`, `force`, `missing`) and closes the dropdown
    - **Validates: Requirements 8.5**

- [x] 6 Allow user to see what's being downloaded
  - [x] 6.1 Show sync command output to the user
    - After a sync completes (success or error), capture the stdout/stderr returned by the backend and display it in a collapsible output panel below the message list
    - In `web/api/sync.py`, ensure the JSON response includes an `output` field containing the combined stdout/stderr from the subprocess (already captured; just confirm it is returned for all modes)
    - In `web/static/index.html`, add a `<details id="sync-output-panel">` element with a `<summary>Sync output</summary>` and a `<pre id="sync-output-text"></pre>` inside; hide it by default with the `hidden` attribute on the `<details>` element
    - In `web/static/app.js`, after a sync response is received, set `#sync-output-text` content to the `output` field from the response and remove the `hidden` attribute from `#sync-output-panel`; if the output is empty or absent, keep the panel hidden
    - In `web/static/style.css`, add styles for `#sync-output-panel`: monospace font, max-height with vertical scroll, subtle background, and a top margin to separate it from the message list
    - _Requirements: 3.4, 4.3, 5.3_
  - [x] 6.2 Validate subprocess output capture in backend (Property 8)
    - **Property 8: Subprocess output is captured and returned for all sync modes**
    - Use Hypothesis `sampled_from(['delta', 'force', 'missing'])` for mode
    - Mock `subprocess.run` to return a `CompletedProcess` with arbitrary stdout/stderr content
    - Assert the JSON response includes an `output` field containing the combined stdout/stderr for every mode
    - Also assert that the subprocess is invoked with `capture_output=True` (or equivalent `stdout=PIPE, stderr=PIPE`) so the background process output is always redirectable and capturable
    - **Validates: Requirements 3.4, 4.3, 5.3**

- [x] 7. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend property tests use Hypothesis; frontend property tests use fast-check (minimum 100 iterations each)
- Unit/example-based tests (split button rendering, dropdown contents, ARIA roles, click-outside, mode→fetch body mapping) complement the property tests and should be added alongside the implementation tasks
- The old `#sync-btn` element and its references in `app.js` and `style.css` must be fully removed as part of tasks 3, 4, and 5
