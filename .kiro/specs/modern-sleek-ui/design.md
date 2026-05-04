# Design Document: Modern Sleek UI

## Overview

This design covers a full visual and structural overhaul of the Gmail Web Viewer single-page application. The current UI is a minimal, utility-first layout with a flat header, a filter bar, and a message table. The redesign introduces a Notion-inspired aesthetic with a collapsible sidebar, a redesigned header, a reading pane, a command palette, a toast notification system, keyboard shortcuts, responsive breakpoints, smooth animations, a density selector, and a complete design-token-driven theming system with light/dark mode.

The implementation is entirely front-end: HTML, CSS, and vanilla JavaScript served by the existing Flask server. No new back-end routes are required. All new behaviour is layered on top of the existing API (`/api/messages`, `/api/labels`, `/api/sync`).

### Key Design Decisions

- **Vanilla JS, no framework.** The existing codebase uses plain JavaScript modules. Introducing React or Vue would require a build pipeline and would break the existing test setup. The redesign stays in vanilla JS.
- **CSS custom properties for all tokens.** A single `:root` block defines every color, spacing, radius, and typography value. A `[data-theme="dark"]` override block swaps colors. A `[data-density="compact"]` override block swaps spacing. This makes theming and density switching a single attribute change on `<html>`.
- **`localStorage` for all preferences.** Theme, sidebar state, reading-pane mode, and density are all persisted to `localStorage` so they survive page reloads.
- **Progressive enhancement for responsive layout.** The layout uses CSS Grid for the main shell. Breakpoints are handled with `@media` queries and a `ResizeObserver` for the reading-pane fallback logic.
- **`fast-check` for property-based tests.** The project already has `fast-check` installed (see `package.json`). All JS property tests use `fast-check`. Python property tests use `hypothesis`.

---

## Architecture

The redesigned app is structured as a shell layout with four primary regions:

```
┌─────────────────────────────────────────────────────────┐
│                        HEADER                           │
├──────────┬──────────────────────────────────────────────┤
│          │                                              │
│ SIDEBAR  │           CONTENT AREA                       │
│          │  (Message List + Reading Pane)               │
│          │                                              │
└──────────┴──────────────────────────────────────────────┘
```

The content area is itself a CSS Grid that adapts based on `Reading_Pane_Mode`:

- `right`: two columns — message list | reading pane
- `below`: one column, two rows — message list / reading pane
- `none`: single column — message list only

### Module Structure

The existing JS files are refactored and extended. New modules are added:

| File | Responsibility |
|---|---|
| `webv2/static/index.html` | Shell markup: header, sidebar, content area, overlay containers |
| `webv2/static/style.css` | All design tokens, layout, component styles, animations |
| `webv2/static/app.js` | App state, bootstrap, event wiring, keyboard shortcuts |
| `webv2/static/themeManager.js` | Theme and density persistence/application |
| `webv2/static/sidebar.js` | Sidebar render, collapse/expand, label navigation |
| `webv2/static/commandPalette.js` | Command palette overlay, filtering, action dispatch |
| `webv2/static/toastManager.js` | Toast queue, render, auto-dismiss |
| `webv2/static/readingPane.js` | Reading pane render, mode switching |
| `webv2/static/filters.js` | Filter bar (existing, extended) |
| `webv2/static/messageList.js` | Message list (existing, extended) |
| `webv2/static/messageDetail.js` | Message detail drawer (existing, extended) |
| `webv2/static/api.js` | API client (existing, unchanged) |

### State Model

The global `state` object is extended:

```javascript
const state = {
  // existing fields
  messages: [],
  total: 0,
  page: 1,
  pageSize: 50,
  query: "",
  label: "",
  isRead: null,
  isOutgoing: null,
  includeDeleted: false,
  selectedMessage: null,
  labels: [],
  error: null,
  sortDir: "desc",

  // new fields
  theme: "light",           // "light" | "dark"
  sidebarCollapsed: false,  // boolean
  readingPaneMode: "right", // "right" | "below" | "none"
  density: "cozy",          // "cozy" | "compact"
  activeLabel: "",          // currently selected sidebar label
  selectedRowIndex: -1,     // keyboard-navigated row index
};
```

---

## Components and Interfaces

### 1. Design Token System (`style.css`)

All visual values are defined as CSS custom properties on `:root`. A `[data-theme="dark"]` block overrides color tokens. A `[data-density="compact"]` block overrides spacing tokens.

**Token categories:**

- **Colors**: `--color-bg`, `--color-surface`, `--color-border`, `--color-text-primary`, `--color-text-secondary`, `--color-accent`, `--color-accent-hover`, `--color-unread-accent`, `--color-success`, `--color-error`, `--color-overlay`
- **Spacing**: `--space-1` through `--space-8` (4px scale)
- **Density tokens**: `--density-row-height`, `--density-padding-y`, `--density-gap`
- **Radii**: `--radius-sm`, `--radius-md`, `--radius-lg`
- **Typography**: `--font-size-xs`, `--font-size-sm`, `--font-size-md`, `--font-size-lg`, `--font-weight-normal`, `--font-weight-medium`, `--font-weight-bold`
- **Shadows**: `--shadow-sm`, `--shadow-md`, `--shadow-lg`
- **Transitions**: `--transition-fast` (120ms), `--transition-normal` (200ms), `--transition-slow` (300ms)

### 2. Theme Manager (`themeManager.js`)

```javascript
const themeManager = {
  STORAGE_KEY_THEME: "gmailviewer-theme",
  STORAGE_KEY_DENSITY: "gmailviewer-density",

  // Reads localStorage or OS preference; applies to <html>
  init(),

  // Sets data-theme on <html>, updates state.theme, persists to localStorage
  // Must complete within 50ms
  applyTheme(theme),   // theme: "light" | "dark"

  // Toggles between light and dark
  toggleTheme(),

  // Sets data-density on <html>, updates state.density, persists to localStorage
  // Must complete within 50ms
  applyDensity(density),  // density: "cozy" | "compact"

  // Toggles between cozy and compact
  toggleDensity(),
};
```

### 3. Sidebar (`sidebar.js`)

```javascript
const sidebar = {
  STORAGE_KEY: "gmailviewer-sidebar-collapsed",

  // Renders sidebar into #sidebar element
  render(),

  // Collapses sidebar with 200ms CSS transition
  collapse(),

  // Expands sidebar with 200ms CSS transition
  expand(),

  // Toggles collapsed state, persists to localStorage
  toggle(),

  // Restores persisted state on init
  init(),
};
```

The sidebar HTML structure:

```html
<nav id="sidebar" aria-label="Navigation">
  <button id="sidebar-toggle" aria-label="Collapse sidebar">...</button>
  <ul role="list">
    <li role="listitem" data-label="">All Mail</li>
    <!-- one <li> per label -->
  </ul>
  <div class="sidebar-read-filter">...</div>
</nav>
```

When collapsed, `#sidebar` gets the class `sidebar--collapsed`. CSS transitions handle the width animation. Icon-only mode shows tooltips via `title` attributes.

### 4. Header (`index.html` + `app.js`)

The header is a fixed `<header>` element containing:

- App logo/name (left)
- Reading pane mode selector (centre)
- Density toggle (centre-right)
- Sync split-button (right)
- Theme toggle (right)
- Command palette hint `⌘K` (right)

The header uses `position: sticky; top: 0` with `backdrop-filter: blur(8px)` and a `box-shadow` that is added via a CSS class when `window.scrollY > 0`.

### 5. Message List (`messageList.js`)

Extended from the existing implementation:

- Card-row layout with left-side accent border for unread messages
- Attachment icon (📎) that opens `Attachment_Popover` on click (not the full detail)
- Hover highlight transition within 120ms
- Empty-state illustration + "No messages found." text
- Keyboard navigation: `J`/`K` move selection, `O`/`Enter` open detail
- `selectedRowIndex` tracked in `state`

### 6. Reading Pane (`readingPane.js`)

```javascript
const readingPane = {
  STORAGE_KEY: "gmailviewer-reading-pane",

  // Renders reading pane content for the selected message
  render(message),

  // Clears the reading pane
  clear(),

  // Applies the given mode to the layout
  applyMode(mode),  // "right" | "below" | "none"

  // Restores persisted mode on init; defaults to "right"
  init(),
};
```

The content area uses a CSS Grid. The `data-reading-pane` attribute on `#content-area` drives the grid layout:

```css
#content-area[data-reading-pane="right"]  { grid-template-columns: 1fr 380px; }
#content-area[data-reading-pane="below"]  { grid-template-rows: auto 1fr; }
#content-area[data-reading-pane="none"]   { grid-template-columns: 1fr; }
```

Responsive fallbacks are applied by a `ResizeObserver` on `#content-area`:
- `right` → `below` when width < 900px
- `below` → `none` when width < 600px

### 7. Command Palette (`commandPalette.js`)

```javascript
const commandPalette = {
  ACTIONS: [
    { id: "sync-delta",    label: "Sync New Data",    run: () => runSync("delta") },
    { id: "sync-force",    label: "Force Sync All",   run: () => runSync("force") },
    { id: "sync-missing",  label: "Sync Missing",     run: () => runSync("missing") },
    { id: "toggle-theme",  label: "Toggle Dark Mode", run: () => themeManager.toggleTheme() },
    { id: "toggle-sidebar",label: "Collapse Sidebar", run: () => sidebar.toggle() },
    { id: "goto-page",     label: "Go to page N",     run: (n) => goToPage(n) },
  ],

  // Opens the palette overlay, focuses input
  open(),

  // Closes the palette overlay
  close(),

  // Filters ACTIONS by query string, renders results
  // Must complete within 100ms
  filter(query),

  // Executes the focused action and closes
  execute(actionId),
};
```

The palette is a `<dialog>` element (or a `role="dialog"` div) rendered at the top of `<body>`. Focus is trapped inside using a focus-trap loop. `Escape` closes it. `ArrowUp`/`ArrowDown` navigate results. `Enter` executes.

### 8. Toast Manager (`toastManager.js`)

```javascript
const toastManager = {
  // Shows a success toast for 3000ms then auto-dismisses
  success(message),

  // Shows an error toast that persists until manually dismissed
  error(message),

  // Dismisses a specific toast with fade-out animation (200ms)
  dismiss(toastId),

  // Internal: renders the toast stack in #toast-container
  _render(),
};
```

Toasts are rendered in `#toast-container` (fixed, bottom-right). Up to 3 are visible at once; additional toasts queue. Each toast has a dismiss button. Success toasts auto-dismiss after 3000ms via `setTimeout`.

### 9. Keyboard Shortcut System (`app.js`)

A single `keydown` listener on `document` dispatches shortcuts. Shortcuts are suppressed when a text input is focused (except `Escape` and `Cmd/Ctrl+K`).

| Key | Action |
|---|---|
| `Cmd/Ctrl+K` | Open Command Palette |
| `J` | Select next message |
| `K` | Select previous message |
| `O` / `Enter` | Open selected message |
| `Escape` | Close Message Detail or Command Palette |
| `R` | Trigger delta sync |
| `?` | Open keyboard shortcut reference modal |

### 10. Attachment Popover and Preview Modal

The attachment icon in the message list row opens an `Attachment_Popover` (a positioned `<div role="listbox">`) listing all attachments. Clicking an attachment entry opens the `Attachment_Preview_Modal`.

The popover closes on outside click or `Escape`. The modal traps focus, supports `Escape` to close, and returns focus to the attachment icon on close.

---

## Data Models

No new back-end data models are required. All new state is client-side.

### localStorage Keys

| Key | Type | Default | Description |
|---|---|---|---|
| `gmailviewer-theme` | `"light" \| "dark"` | OS preference | Active theme |
| `gmailviewer-sidebar-collapsed` | `"true" \| "false"` | `"false"` | Sidebar state |
| `gmailviewer-reading-pane` | `"right" \| "below" \| "none"` | `"right"` | Reading pane mode |
| `gmailviewer-density` | `"cozy" \| "compact"` | `"cozy"` | Density mode |

### Theme Application Model

```
init()
  → read localStorage["gmailviewer-theme"]
  → if present: applyTheme(stored)
  → else: applyTheme(window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")

applyTheme(theme)
  → document.documentElement.setAttribute("data-theme", theme)
  → state.theme = theme
  → localStorage.setItem("gmailviewer-theme", theme)
```

### Density Application Model

```
applyDensity(density)
  → document.documentElement.setAttribute("data-density", density)
  → state.density = density
  → localStorage.setItem("gmailviewer-density", density)
```

### Reading Pane Mode Model

```
applyMode(mode)
  → effectiveMode = resolveResponsiveFallback(mode, viewportWidth)
  → document.getElementById("content-area").setAttribute("data-reading-pane", effectiveMode)
  → state.readingPaneMode = mode  // store the user's intent, not the effective mode
  → localStorage.setItem("gmailviewer-reading-pane", mode)
```

`resolveResponsiveFallback(mode, width)`:
- `"right"` + width < 900 → `"below"`
- `"below"` + width < 600 → `"none"`
- otherwise → `mode`

### Toast Data Model

```javascript
{
  id: string,        // unique ID (e.g. crypto.randomUUID())
  type: "success" | "error",
  message: string,
  autoDismiss: boolean,  // true for success, false for error
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Theme application is immediate and consistent

*For any* theme value (`"light"` or `"dark"`), calling `applyTheme(theme)` SHALL set `document.documentElement.getAttribute("data-theme")` to that value, update `state.theme` to that value, and write that value to `localStorage["gmailviewer-theme"]` — all three in agreement.

**Validates: Requirements 2.2, 2.3, 2.4**

### Property 2: Theme init restores persisted preference

*For any* theme value stored in `localStorage["gmailviewer-theme"]`, calling `themeManager.init()` SHALL result in `document.documentElement.getAttribute("data-theme")` equalling the stored value.

**Validates: Requirements 2.5**

### Property 3: Density application is immediate and consistent

*For any* density value (`"cozy"` or `"compact"`), calling `applyDensity(density)` SHALL set `document.documentElement.getAttribute("data-density")` to that value, update `state.density` to that value, and write that value to `localStorage["gmailviewer-density"]` — all three in agreement.

**Validates: Requirements 13.3, 13.4, 13.6, 13.8**

### Property 4: Reading pane mode is persisted and restored

*For any* reading pane mode value (`"right"`, `"below"`, or `"none"`), calling `readingPane.applyMode(mode)` SHALL write that value to `localStorage["gmailviewer-reading-pane"]`, and a subsequent call to `readingPane.init()` SHALL restore `state.readingPaneMode` to that value.

**Validates: Requirements 6.3, 6.4**

### Property 5: Responsive reading pane fallback is monotone

*For any* user-selected reading pane mode and any viewport width, the effective mode returned by `resolveResponsiveFallback(mode, width)` SHALL never be "more expansive" than the user's selected mode. Specifically: if the user selected `"none"`, the effective mode is always `"none"`; if the user selected `"below"`, the effective mode is `"below"` or `"none"`; if the user selected `"right"`, the effective mode is `"right"`, `"below"`, or `"none"`.

**Validates: Requirements 6.12, 6.13**

### Property 6: Command palette filter is a subset

*For any* query string and any set of actions, the filtered results returned by `commandPalette.filter(query)` SHALL be a subset of the full action list — no result appears that was not in the original list.

**Validates: Requirements 7.3**

### Property 7: Toast type determines dismiss behaviour

*For any* toast created via `toastManager.success(message)`, the toast SHALL have `autoDismiss: true`. *For any* toast created via `toastManager.error(message)`, the toast SHALL have `autoDismiss: false`.

**Validates: Requirements 8.1, 8.2**

### Property 8: Toast queue is FIFO and bounded

*For any* sequence of toast additions, the visible toasts SHALL appear in the order they were added (FIFO), and the number of simultaneously visible toasts SHALL never exceed 3.

**Validates: Requirements 8.3, 8.4**

### Property 9: Sidebar collapsed state round-trips through localStorage

*For any* collapsed state value (`true` or `false`), calling `sidebar.toggle()` to reach that state and then calling `sidebar.init()` in a fresh context SHALL restore `state.sidebarCollapsed` to that value.

**Validates: Requirements 3.6, 3.7**

---

## Error Handling

### Theme / Density / Preference Persistence

`localStorage` access can throw in private-browsing mode or when storage is full. All `localStorage` reads and writes are wrapped in `try/catch`. On failure, the app falls back to the default value (light theme, cozy density, right reading pane, expanded sidebar) and continues without persisting.

### Sync Errors

Sync errors are surfaced via the toast system (error toast) rather than the existing error banner. The error banner is retained as a fallback for non-sync errors (e.g., failed message fetch).

### Command Palette Action Errors

If a command palette action throws, the error is caught, the palette closes, and an error toast is shown with the error message.

### Reading Pane Load Errors

If the message fetch for the reading pane fails, the reading pane displays an inline error state ("Failed to load message") rather than leaving the pane blank.

### Attachment Popover / Preview Errors

If the attachment data URL fails to load (e.g., 404), the preview modal shows a fallback message with a download link.

### Reduced Motion

All CSS transitions check `@media (prefers-reduced-motion: reduce)` and reduce to a simple `opacity` transition of ≤ 100ms.

---

## Testing Strategy

### Overview

The feature is primarily UI/CSS/JS. Most acceptance criteria are about visual behaviour, layout, and user interaction. Property-based testing applies to the pure logic functions: theme/density/preference management, reading pane mode resolution, command palette filtering, and toast queue management.

### Unit Tests (Jest + jsdom)

Unit tests cover specific examples and edge cases for each component:

- `themeManager`: init with stored preference, init with no preference (OS fallback), applyTheme sets attribute + state + localStorage, toggleTheme flips correctly
- `sidebar`: collapse/expand sets correct CSS class, init restores state, off-canvas mode at < 768px
- `readingPane`: applyMode sets correct grid attribute, init defaults to `"right"`, responsive fallback thresholds
- `commandPalette`: open focuses input, filter returns correct subset, execute calls action and closes, Escape closes without executing
- `toastManager`: success toast auto-dismisses after 3000ms, error toast persists, dismiss removes with animation, FIFO order, max 3 visible
- `messageList`: unread row has accent border class, deleted row has strikethrough class, empty state renders correct text, attachment icon click opens popover

### Property-Based Tests (Jest + fast-check)

Each property test runs a minimum of 100 iterations.

**Tag format:** `// Feature: modern-sleek-ui, Property N: <property_text>`

**Property 1 test** — `themeManager.applyTheme`:
- Generator: `fc.constantFrom("light", "dark")`
- Assert: after `applyTheme(theme)`, `html.getAttribute("data-theme") === theme`, `state.theme === theme`, `localStorage.getItem("gmailviewer-theme") === theme`

**Property 2 test** — `themeManager.init` restores:
- Generator: `fc.constantFrom("light", "dark")`
- Setup: write theme to localStorage, call `init()`
- Assert: `html.getAttribute("data-theme") === storedTheme`

**Property 3 test** — `applyDensity`:
- Generator: `fc.constantFrom("cozy", "compact")`
- Assert: after `applyDensity(density)`, all three (attribute, state, localStorage) agree

**Property 4 test** — reading pane round-trip:
- Generator: `fc.constantFrom("right", "below", "none")`
- Assert: `applyMode(mode)` → `localStorage` has `mode` → `init()` → `state.readingPaneMode === mode`

**Property 5 test** — responsive fallback monotonicity:
- Generator: `fc.tuple(fc.constantFrom("right", "below", "none"), fc.integer({ min: 0, max: 2000 }))`
- Assert: `resolveResponsiveFallback(mode, width)` never returns a more expansive mode than `mode`

**Property 6 test** — command palette filter subset:
- Generator: `fc.tuple(fc.string(), fc.array(fc.record({ id: fc.string(), label: fc.string() })))`
- Assert: every item in `filter(query, actions)` is contained in `actions`

**Property 7 test** — toast type determines autoDismiss:
- Generator: `fc.tuple(fc.constantFrom("success", "error"), fc.string())`
- Assert: `success(msg).autoDismiss === true`, `error(msg).autoDismiss === false`

**Property 8 test** — toast queue FIFO and bounded:
- Generator: `fc.array(fc.string(), { minLength: 1, maxLength: 10 })`
- Assert: visible toasts ≤ 3, order matches insertion order

**Property 9 test** — sidebar state round-trip:
- Generator: `fc.boolean()`
- Assert: set state → persist → init → restored state matches

### Integration Tests

- Full page load: header, sidebar, message list, and filter bar all render
- Theme toggle in header: clicking toggles `data-theme` on `<html>`
- Sidebar collapse: clicking toggle adds `sidebar--collapsed` class
- Command palette: `Ctrl+K` opens overlay, `Escape` closes it
- Reading pane mode selector: switching mode updates `data-reading-pane` on `#content-area`
- Toast on sync success: after a successful sync, a success toast appears
- Toast on sync failure: after a failed sync, an error toast appears and persists

### Accessibility Checks

- All interactive elements have visible focus indicators
- ARIA roles and labels are present on Sidebar, Command Palette, Toasts, Message List rows
- Focus trap works in Command Palette and Attachment Preview Modal
- `aria-live="polite"` region announces toasts to screen readers
