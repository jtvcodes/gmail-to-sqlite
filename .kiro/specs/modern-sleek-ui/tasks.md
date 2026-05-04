# Implementation Plan: Modern Sleek UI

## Overview

Implement a full visual and structural overhaul of the Gmail Web Viewer SPA using vanilla JavaScript, CSS custom properties, and the existing Flask back-end. The implementation is layered incrementally: design tokens and theming first, then layout shell, then individual feature modules, then integration wiring.

## Tasks

- [-] 1. Set up design token system and base CSS
  - Create/replace `webv2/static/style.css` with all CSS custom properties on `:root`: color tokens, spacing scale (`--space-1` through `--space-8`), density tokens (`--density-row-height`, `--density-padding-y`, `--density-gap`), radii, typography, shadows, and transition duration variables
  - Add `[data-theme="dark"]` selector that overrides all color tokens with dark-mode equivalents
  - Add `[data-density="compact"]` selector that overrides density spacing tokens
  - Add `@media (prefers-reduced-motion: reduce)` block that reduces all transitions to a simple opacity fade ≤ 100 ms
  - Ensure no hard-coded color, spacing, or typography values remain in component CSS rules
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 12.2, 12.3, 13.5_

- [ ] 2. Implement Theme Manager and Density Manager
  - [~] 2.1 Create `webv2/static/themeManager.js` with `init()`, `applyTheme(theme)`, `toggleTheme()`, `applyDensity(density)`, and `toggleDensity()` methods
    - `applyTheme` sets `data-theme` on `<html>`, updates `state.theme`, and writes to `localStorage["gmailviewer-theme"]` within 50 ms
    - `applyDensity` sets `data-density` on `<html>`, updates `state.density`, and writes to `localStorage["gmailviewer-density"]` within 50 ms
    - `init()` reads `localStorage` first; falls back to `prefers-color-scheme` for theme and `"cozy"` for density; wraps all `localStorage` access in `try/catch`
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 13.3, 13.4, 13.6, 13.7, 13.8_

  - [~] 2.2 Write property test for `applyTheme` (Property 1)
    - **Property 1: Theme application is immediate and consistent**
    - **Validates: Requirements 2.2, 2.3, 2.4**
    - Generator: `fc.constantFrom("light", "dark")`; assert `data-theme`, `state.theme`, and `localStorage` all agree after `applyTheme(theme)`

  - [~] 2.3 Write property test for `themeManager.init` restores persisted preference (Property 2)
    - **Property 2: Theme init restores persisted preference**
    - **Validates: Requirements 2.5**
    - Generator: `fc.constantFrom("light", "dark")`; write to `localStorage`, call `init()`, assert `data-theme` matches stored value

  - [~] 2.4 Write property test for `applyDensity` (Property 3)
    - **Property 3: Density application is immediate and consistent**
    - **Validates: Requirements 13.3, 13.4, 13.6, 13.8**
    - Generator: `fc.constantFrom("cozy", "compact")`; assert `data-density`, `state.density`, and `localStorage` all agree after `applyDensity(density)`

  - [~] 2.5 Write unit tests for `themeManager`
    - Test `toggleTheme` flips between `"light"` and `"dark"` correctly
    - Test `init` with no stored preference applies OS `prefers-color-scheme` value
    - Test `localStorage` failure falls back to default without throwing
    - _Requirements: 2.2, 2.5, 13.7_

- [~] 3. Implement HTML shell layout
  - Update `webv2/static/index.html` with the four-region shell: fixed `<header>`, `<nav id="sidebar">`, `<main id="content-area">`, and overlay containers (`#toast-container`, command palette placeholder, attachment modal placeholder)
  - Apply CSS Grid to the main shell (`header / sidebar / content-area`)
  - Add `data-reading-pane` attribute to `#content-area`; define grid rules for `right`, `below`, and `none` modes in `style.css`
  - Add `position: sticky; top: 0; backdrop-filter: blur(8px)` to header; add scroll-shadow class toggled by `window.scrollY > 0`
  - Assign ARIA roles and labels to all structural regions (Sidebar `aria-label="Navigation"`, Message List `role="list"`, etc.)
  - _Requirements: 4.1, 4.2, 4.4, 10.4, 11.1_

- [ ] 4. Implement Sidebar
  - [~] 4.1 Create `webv2/static/sidebar.js` with `render()`, `collapse()`, `expand()`, `toggle()`, and `init()` methods
    - `render()` populates `#sidebar` with "All Mail", per-label `<li>` items, and the read/unread filter toggle
    - `collapse()` / `expand()` add/remove `sidebar--collapsed` CSS class with a 200 ms CSS transition
    - `toggle()` persists state to `localStorage["gmailviewer-sidebar-collapsed"]` wrapped in `try/catch`
    - `init()` restores persisted collapsed state; defaults to expanded
    - Collapsed state shows icon-only items with `title` tooltips
    - Off-canvas mode (viewport < 768 px): sidebar renders as a hidden overlay drawer
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 10.3_

  - [~] 4.2 Write property test for sidebar state round-trip (Property 9)
    - **Property 9: Sidebar collapsed state round-trips through localStorage**
    - **Validates: Requirements 3.6, 3.7**
    - Generator: `fc.boolean()`; set state via `toggle()`, call `init()` in fresh context, assert `state.sidebarCollapsed` matches

  - [~] 4.3 Write unit tests for `sidebar`
    - Test `collapse()` adds `sidebar--collapsed` class
    - Test `expand()` removes `sidebar--collapsed` class
    - Test `init()` restores persisted state
    - Test off-canvas mode renders at viewport < 768 px
    - _Requirements: 3.4, 3.5, 3.7, 3.8_

- [ ] 5. Implement Reading Pane
  - [~] 5.1 Create `webv2/static/readingPane.js` with `render(message)`, `clear()`, `applyMode(mode)`, and `init()` methods
    - `applyMode(mode)` calls `resolveResponsiveFallback(mode, viewportWidth)` and sets `data-reading-pane` on `#content-area`; stores the user's intent (not effective mode) to `localStorage["gmailviewer-reading-pane"]`
    - Export `resolveResponsiveFallback(mode, width)` as a pure function: `"right"` + width < 900 → `"below"`; `"below"` + width < 600 → `"none"`; otherwise → `mode`
    - `init()` restores persisted mode; defaults to `"right"`
    - Attach a `ResizeObserver` on `#content-area` to re-apply fallback logic on resize
    - `render(message)` displays subject, sender, date, labels, body, and attachments in `#reading-pane`
    - On message fetch failure, display inline error state "Failed to load message"
    - _Requirements: 6.1, 6.3, 6.4, 6.6, 6.8, 6.9, 6.10, 6.12, 6.13_

  - [~] 5.2 Write property test for reading pane mode round-trip (Property 4)
    - **Property 4: Reading pane mode is persisted and restored**
    - **Validates: Requirements 6.3, 6.4**
    - Generator: `fc.constantFrom("right", "below", "none")`; call `applyMode(mode)`, then `init()`, assert `state.readingPaneMode === mode`

  - [~] 5.3 Write property test for responsive fallback monotonicity (Property 5)
    - **Property 5: Responsive reading pane fallback is monotone**
    - **Validates: Requirements 6.12, 6.13**
    - Generator: `fc.tuple(fc.constantFrom("right", "below", "none"), fc.integer({ min: 0, max: 2000 }))`; assert `resolveResponsiveFallback(mode, width)` never returns a more expansive mode than `mode`

  - [~] 5.4 Write unit tests for `readingPane`
    - Test `applyMode("right")` sets `data-reading-pane="right"` on `#content-area`
    - Test `init()` defaults to `"right"` when no preference stored
    - Test responsive fallback thresholds (900 px and 600 px boundaries)
    - _Requirements: 6.1, 6.4, 6.12, 6.13_

- [ ] 6. Implement Command Palette
  - [~] 6.1 Create `webv2/static/commandPalette.js` with `open()`, `close()`, `filter(query)`, and `execute(actionId)` methods
    - Define `ACTIONS` array with the six built-in actions: "Sync New Data", "Force Sync All", "Sync Missing", "Toggle Dark Mode", "Collapse Sidebar", "Go to page N"
    - `open()` renders the `<dialog>` (or `role="dialog"` div) overlay and focuses the text input immediately
    - `filter(query)` returns matching actions within 100 ms; renders results list
    - `execute(actionId)` calls the action's `run()` function and closes the palette; wraps in `try/catch` — on error, closes palette and shows error toast
    - `close()` hides the overlay without executing any action
    - Implement focus trap: `Tab`/`Shift+Tab` cycle within the palette
    - `ArrowDown`/`ArrowUp` move focus between results; `Enter` executes focused result; `Escape` closes
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 11.3_

  - [~] 6.2 Write property test for command palette filter subset (Property 6)
    - **Property 6: Command palette filter is a subset**
    - **Validates: Requirements 7.3**
    - Generator: `fc.tuple(fc.string(), fc.array(fc.record({ id: fc.string(), label: fc.string() })))`; assert every item in `filter(query, actions)` is contained in `actions`

  - [~] 6.3 Write unit tests for `commandPalette`
    - Test `open()` focuses the input element
    - Test `filter("")` returns all actions
    - Test `filter("sync")` returns only sync-related actions
    - Test `execute()` calls the action's `run()` and closes the palette
    - Test `Escape` closes without executing
    - _Requirements: 7.2, 7.3, 7.5, 7.6_

- [ ] 7. Implement Toast Manager
  - [~] 7.1 Create `webv2/static/toastManager.js` with `success(message)`, `error(message)`, `dismiss(toastId)`, and `_render()` methods
    - Each toast has `{ id, type, message, autoDismiss }` — `success` sets `autoDismiss: true`, `error` sets `autoDismiss: false`
    - `_render()` displays up to 3 toasts in `#toast-container` (fixed, bottom-right, 8 px gap); additional toasts queue in FIFO order
    - Success toasts auto-dismiss after 3000 ms via `setTimeout`
    - `dismiss(toastId)` removes the toast with a 200 ms fade-out animation
    - Apply active theme's Design_Tokens (green accent for success, red accent for error)
    - Add `aria-live="polite"` region for screen reader announcements
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 11.4_

  - [~] 7.2 Write property test for toast type determines autoDismiss (Property 7)
    - **Property 7: Toast type determines dismiss behaviour**
    - **Validates: Requirements 8.1, 8.2**
    - Generator: `fc.tuple(fc.constantFrom("success", "error"), fc.string())`; assert `success(msg).autoDismiss === true` and `error(msg).autoDismiss === false`

  - [~] 7.3 Write property test for toast queue FIFO and bounded (Property 8)
    - **Property 8: Toast queue is FIFO and bounded**
    - **Validates: Requirements 8.3, 8.4**
    - Generator: `fc.array(fc.string(), { minLength: 1, maxLength: 10 })`; assert visible toasts ≤ 3 and order matches insertion order

  - [~] 7.4 Write unit tests for `toastManager`
    - Test success toast auto-dismisses after 3000 ms (use fake timers)
    - Test error toast persists after 3000 ms
    - Test `dismiss()` removes toast with fade-out
    - Test FIFO order when more than 3 toasts are queued
    - _Requirements: 8.1, 8.2, 8.4, 8.5_

- [~] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Extend Message List
  - [~] 9.1 Update `webv2/static/messageList.js` with the redesigned card-row layout
    - Unread rows: apply heavier font weight and left-side accent border using `--color-unread-accent`
    - Deleted rows: apply strikethrough and reduced opacity
    - Hover highlight: CSS transition within 120 ms using `--transition-fast`
    - Attachment icon (📎) on rows where `has_attachments` is true; clicking opens `Attachment_Popover` (not the full detail)
    - Empty state: centred illustration and "No messages found." text when message list is empty
    - Pagination controls: current page, total pages, Previous/Next buttons
    - Sortable column headers: clicking toggles sort direction and re-fetches
    - Track `state.selectedRowIndex` for keyboard navigation
    - Assign ARIA roles to list rows (`role="row"` or `role="listitem"`)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 11.1_

  - [~] 9.2 Write unit tests for `messageList`
    - Test unread row has accent border class
    - Test deleted row has strikethrough class
    - Test empty state renders "No messages found."
    - Test attachment icon click opens popover (not detail)
    - _Requirements: 5.2, 5.3, 5.5, 5.6_

- [ ] 10. Implement Attachment Popover and Preview Modal
  - [~] 10.1 Add `Attachment_Popover` component to `webv2/static/messageList.js` (or a new `attachments.js` module)
    - Popover is a positioned `<div role="listbox">` adjacent to the attachment icon
    - Each entry shows filename, file-type icon, and file size
    - Closes on outside click or `Escape`; returns focus to the attachment icon on close
    - _Requirements: 14.1, 14.2, 14.10_

  - [~] 10.2 Add `Attachment_Preview_Modal` component
    - Opens when user clicks an attachment entry in the popover
    - Supported preview types (images, PDF): render inline (`<img>` or embedded viewer)
    - Unsupported types: show file-type icon and filename as fallback
    - Action controls: Download button, Print button (scoped to attachment content), Close button
    - Traps focus within modal; `Escape` closes and returns focus to the attachment icon
    - Download, Print, and Close are reachable via `Tab` and activatable via `Enter`/`Space`
    - On load failure: show fallback message with download link
    - Apply active theme's Design_Tokens
    - _Requirements: 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10, 11.3_

  - [~] 10.3 Write unit tests for attachment components
    - Test popover opens with correct attachment list
    - Test popover closes on outside click and `Escape`
    - Test modal opens inline preview for supported types
    - Test modal shows fallback for unsupported types
    - Test focus trap in modal
    - _Requirements: 14.1, 14.2, 14.4, 14.5, 14.8_

- [ ] 11. Implement Keyboard Shortcut System and Header Controls
  - [~] 11.1 Update `webv2/static/app.js` with the global `keydown` listener and shortcut dispatch
    - Shortcuts: `Cmd/Ctrl+K` → open Command Palette; `J` → next message; `K` → previous message; `O`/`Enter` → open selected message; `Escape` → close detail or palette; `R` → delta sync; `?` → open shortcut reference modal
    - Suppress shortcuts when a text input is focused (except `Escape` and `Cmd/Ctrl+K`)
    - Implement `?` shortcut reference modal listing all shortcuts
    - _Requirements: 9.1, 9.2, 9.3_

  - [~] 11.2 Wire header controls in `index.html` and `app.js`
    - Theme toggle button: calls `themeManager.toggleTheme()`
    - Reading pane mode selector: calls `readingPane.applyMode(mode)`
    - Density toggle: calls `themeManager.toggleDensity()`
    - Sync split-button: triggers sync operations
    - `⌘K` hint label in header
    - Scroll listener: adds drop-shadow class to header when `window.scrollY > 0`
    - _Requirements: 4.1, 4.3, 6.2, 13.2_

  - [~] 11.3 Write unit tests for keyboard shortcuts
    - Test `Cmd/Ctrl+K` opens command palette
    - Test `J`/`K` update `state.selectedRowIndex`
    - Test shortcuts are suppressed when text input is focused
    - Test `Escape` closes open overlays
    - _Requirements: 9.1, 9.2_

- [~] 12. Implement Responsive Layout Breakpoints
  - Add `@media` query rules in `style.css` for the three breakpoints:
    - ≥ 1200 px: sidebar expanded alongside message list
    - 768–1199 px: sidebar in collapsed icon-only mode by default
    - < 768 px: sidebar hidden; hamburger button in header opens off-canvas overlay
  - Ensure fluid widths and CSS grid/flexbox so no horizontal scrollbar appears at ≥ 320 px
  - Wire hamburger button in header to toggle off-canvas sidebar overlay
  - Ensure layout reflows within one animation frame on resize (no page reload)
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [~] 13. Apply Smooth Animations and Transitions
  - Audit all interactive components and ensure CSS transitions are applied to: sidebar collapse/expand, message detail open/close, dropdown open/close, hover states on rows and buttons, and toast appear/dismiss
  - Verify all animations use `transform` and `opacity` rather than layout-triggering properties (except where layout change is the intent)
  - Verify `@media (prefers-reduced-motion: reduce)` block reduces all non-essential animations to ≤ 100 ms opacity fade
  - _Requirements: 12.1, 12.2, 12.3_

- [~] 14. Accessibility audit and fixes
  - Verify all interactive elements have correct ARIA roles, labels, and live regions: Sidebar, Message_List rows, Message_Detail, Command_Palette, Sync_Control, Toasts
  - Verify logical tab order across all interactive elements
  - Verify focus traps work in Command_Palette, Message_Detail drawer, and Attachment_Preview_Modal; focus returns to triggering element on close
  - Verify `aria-live="polite"` region announces toasts
  - Verify visible focus indicators meet WCAG_AA contrast on all interactive elements
  - Verify unread status uses both font weight and accent border (not color alone); error state uses both color and icon
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [ ] 15. Wire all modules together in `app.js` and final integration
  - [~] 15.1 Update `webv2/static/app.js` bootstrap sequence
    - Call `themeManager.init()`, `sidebar.init()`, `readingPane.init()` on page load
    - Extend global `state` object with new fields: `theme`, `sidebarCollapsed`, `readingPaneMode`, `density`, `activeLabel`, `selectedRowIndex`
    - Wire single-click on message row: if `readingPaneMode` is `right` or `below`, load into reading pane; if `none`, open full detail
    - Wire double-click on message row: always open full Message_Detail window
    - Wire `Escape` in Message_Detail to close and restore focus to previously selected row
    - Replace existing error banner for sync errors with error toast; retain banner for non-sync errors
    - _Requirements: 6.5, 6.6, 6.7, 6.11_

  - [~] 15.2 Wire sync operations to toast notifications
    - On sync success: call `toastManager.success("Sync complete")`
    - On sync failure: call `toastManager.error(descriptiveMessage)`
    - _Requirements: 8.1, 8.2_

  - [~] 15.3 Write integration tests
    - Full page load: header, sidebar, message list, and filter bar all render
    - Theme toggle: clicking toggles `data-theme` on `<html>`
    - Sidebar collapse: clicking toggle adds `sidebar--collapsed` class
    - `Ctrl+K` opens command palette overlay; `Escape` closes it
    - Reading pane mode selector: switching mode updates `data-reading-pane` on `#content-area`
    - Sync success: success toast appears; sync failure: error toast appears and persists
    - _Requirements: 2.2, 3.4, 6.2, 7.1, 7.6, 8.1, 8.2_

- [~] 16. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (Properties 1–9 from the design document)
- Unit tests validate specific examples and edge cases
- All JS property tests use `fast-check`; all Python property tests use `hypothesis`
- The implementation is entirely front-end — no new back-end routes are required
