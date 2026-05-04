# Design Document: Sync Button Dropdown

## Overview

This feature replaces the single `⟳ Sync` button in the Gmail Web Viewer header with a **split button** control. The primary segment triggers a fast delta sync ("Sync New Data"), while a chevron toggle opens a dropdown menu exposing two additional modes: "Sync All (Forced)" and "Sync Missing". The backend `/api/sync` endpoint is extended to accept a `mode` parameter that routes to the correct `main.py` subprocess flags.

The change touches four files:

| File | Change |
|---|---|
| `web/static/index.html` | Replace `<button id="sync-btn">` with split button HTML |
| `web/static/app.js` | Update `runSync`, `setLoading`, and add dropdown state management |
| `web/api/sync.py` | Accept `mode` in POST body; build correct subprocess command |
| `web/static/style.css` | Add split button and dropdown menu styles |

No new dependencies are introduced. The existing Flask backend, vanilla-JS frontend, and `main.py` CLI are reused as-is.

---

## Architecture

The feature is a pure UI/API extension with no new services or data stores.

```mermaid
flowchart LR
    subgraph Browser
        A[Split Button\nprimary segment] -->|click| C[runSync('delta')]
        B[Dropdown Toggle] -->|click| D[toggleDropdown]
        D --> E[Dropdown Menu]
        E -->|Sync New Data| C
        E -->|Sync All Forced| F[runSync('force')]
        E -->|Sync Missing| G[runSync('missing')]
    end

    subgraph Flask API
        C & F & G -->|POST /api/sync\n{mode}| H[run_sync()]
        H -->|mode=delta| I[main.py sync --delta]
        H -->|mode=force| J[main.py sync --force]
        H -->|mode=missing| K[main.py sync]
    end
```

The frontend remains a vanilla-JS SPA with no build step. State is managed in the existing `state` object in `app.js`. The dropdown open/closed state is tracked in a module-level variable.

---

## Components and Interfaces

### 1. Split Button HTML Structure (`index.html`)

The existing `<button id="sync-btn">` is replaced with a wrapper `<div>` containing two focusable elements:

```html
<div class="sync-split-btn" id="sync-split-btn">
  <button
    id="sync-primary-btn"
    class="sync-primary"
    onclick="runSync('delta')"
  >⟳ Sync New Data</button>
  <button
    id="sync-toggle-btn"
    class="sync-toggle"
    aria-haspopup="true"
    aria-expanded="false"
    aria-label="More sync options"
    onclick="toggleSyncDropdown(event)"
  >▾</button>
  <ul
    id="sync-dropdown"
    class="sync-dropdown-menu"
    role="menu"
    hidden
  >
    <li role="menuitem" tabindex="-1" onclick="runSync('delta')">⟳ Sync New Data</li>
    <li role="menuitem" tabindex="-1" onclick="runSync('force')">⟳ Sync All (Forced)</li>
    <li role="menuitem" tabindex="-1" onclick="runSync('missing')">⟳ Sync Missing</li>
  </ul>
</div>
```

### 2. JavaScript API (`app.js`)

#### `runSync(mode)`

Replaces the existing `runSync()`. Accepts a `mode` string (`'delta'`, `'force'`, `'missing'`).

```
runSync(mode: 'delta' | 'force' | 'missing') → Promise<void>
```

- Disables both split button segments via `setLoading(true, labelForMode(mode))`.
- POSTs `{ mode }` as JSON to `/api/sync`.
- On success: calls `loadLabels()` then `loadMessages()`.
- On error: sets `state.error` and calls `renderError()`.
- Always calls `setLoading(false)` in `finally`.

#### `setLoading(on, label)` (updated)

Extended to target the split button segments instead of the old `#sync-btn`:

- `on=true`: disables `#sync-primary-btn` and `#sync-toggle-btn`; sets primary button text to `"⟳ Syncing…"`.
- `on=false`: re-enables both; restores primary button text to `"⟳ Sync New Data"`.

#### `toggleSyncDropdown(event)`

New function. Manages dropdown open/closed state.

```
toggleSyncDropdown(event: MouseEvent) → void
```

- If a sync is in progress (loading), does nothing.
- Toggles `hidden` attribute on `#sync-dropdown`.
- Updates `aria-expanded` on `#sync-toggle-btn`.
- Registers/removes a one-shot `document` click listener to close the menu when clicking outside.

#### `closeSyncDropdown()`

Closes the dropdown and restores `aria-expanded="false"`.

#### Keyboard navigation

An `keydown` listener on `#sync-dropdown` handles:
- `ArrowDown` / `ArrowUp`: moves focus between `[role="menuitem"]` elements.
- `Escape`: calls `closeSyncDropdown()` and returns focus to `#sync-toggle-btn`.
- `Enter` / `Space` on a focused item: triggers the item's `onclick`.

### 3. Backend Sync Mode Routing (`sync.py`)

`run_sync()` is extended to read an optional `mode` field from the JSON request body and build the subprocess command accordingly:

```
mode = request.get_json(silent=True, force=True).get('mode', 'missing')
```

| `mode` value | Subprocess flags |
|---|---|
| `'delta'` | `['sync', '--delta', '--data-dir', data_dir]` |
| `'force'` | `['sync', '--force', '--data-dir', data_dir]` |
| `'missing'` (or absent) | `['sync', '--data-dir', data_dir]` |
| anything else | HTTP 400 |

All existing timeout (300 s), error-handling, and output-capture logic is preserved unchanged for every mode.

### 4. CSS (`style.css`)

New rules replace the `#sync-btn` block:

- `.sync-split-btn`: `display: inline-flex`, no gap between segments, `border-radius: 4px` on outer corners only.
- `.sync-primary`: left segment, rounded left corners, normal padding.
- `.sync-toggle`: right segment, narrow width (~28 px), rounded right corners, left border separator.
- `.sync-dropdown-menu`: absolutely positioned below the toggle, `z-index: 150`, white background, border, shadow, `list-style: none`.
- `.sync-dropdown-menu li`: hover highlight, cursor pointer, padding.
- Disabled state: both segments get `opacity: 0.6; cursor: default` when `disabled`.

---

## Data Models

No new persistent data models are introduced.

### API Request Body (extended)

```json
{
  "mode": "delta" | "force" | "missing"
}
```

`mode` is optional; omitting it is equivalent to `"missing"`.

### API Response (unchanged)

Success:
```json
{ "ok": true, "output": "<subprocess stdout+stderr>" }
```

Error:
```json
{ "error": "<message>" }
```

HTTP 400 for invalid mode:
```json
{ "error": "Invalid mode 'xyz'. Must be one of: delta, force, missing." }
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Loading state is a round-trip for split button segments

*For any* initial enabled/label state of the split button, calling `setLoading(true)` followed by `setLoading(false)` SHALL restore both segments to their original enabled state with their original labels.

**Validates: Requirements 1.6**

---

### Property 2: Backend mode routing correctness

*For any* valid `mode` value in `{'delta', 'force', 'missing'}` and any valid `data_dir` path, the subprocess command built by `run_sync()` SHALL contain exactly the flags that correspond to that mode:
- `delta` → includes `--delta`, excludes `--force`
- `force` → includes `--force`, excludes `--delta`
- `missing` (or absent) → includes neither `--delta` nor `--force`

**Validates: Requirements 3.3, 4.2, 5.2, 6.2, 6.3, 6.4**

---

### Property 3: Invalid mode values are rejected

*For any* string value not in `{'delta', 'force', 'missing'}`, the Sync_API SHALL return HTTP 400 with a non-empty error message body.

**Validates: Requirements 6.1, 6.5**

---

### Property 4: Error messages are surfaced to the UI

*For any* error message string returned by the Sync_API (for any mode), the UI error banner SHALL display exactly that error message after the sync call completes.

**Validates: Requirements 3.5, 4.4, 5.4**

---

### Property 5: Loading overlay label matches sync mode

*For any* sync mode in `{'delta', 'force', 'missing'}`, the loading overlay label displayed during the sync SHALL be the mode-specific string:
- `delta` → `"Syncing new messages…"`
- `force` → `"Force-syncing all messages…"`
- `missing` → `"Syncing missing messages…"`

**Validates: Requirements 7.1, 7.2, 7.3**

---

### Property 6: `aria-expanded` accurately reflects dropdown state

*For any* sequence of open/close operations on the dropdown, the `aria-expanded` attribute on the toggle button SHALL equal `"true"` when the dropdown is visible and `"false"` when it is hidden.

**Validates: Requirements 8.6**

---

### Property 7: Keyboard Enter on any menu item triggers its sync mode

*For any* menu item in the dropdown, pressing Enter while that item has focus SHALL trigger `runSync` with the mode corresponding to that item and close the dropdown.

**Validates: Requirements 8.5**

---

## Error Handling

| Scenario | Handling |
|---|---|
| Invalid `mode` in POST body | HTTP 400 with descriptive message; no subprocess spawned |
| `main.py` not found | HTTP 500 (existing behaviour, preserved for all modes) |
| Subprocess exits non-zero | HTTP 500 with stdout+stderr (existing behaviour) |
| Subprocess timeout (>300 s) | HTTP 504 (existing behaviour) |
| Network error in browser | `state.error = "Network error — could not reach the server"` |
| API returns error JSON | `state.error = data.error`; displayed in error banner |
| Dropdown clicked while loading | Toggle is `disabled`; no action taken |
| Click outside open dropdown | Dropdown closes; no sync triggered |

---

## Testing Strategy

### Unit / Example-Based Tests

These cover specific interactions and structural checks where input variation does not add value:

- **Split button rendering**: assert the DOM contains `.sync-split-btn`, `#sync-primary-btn`, `#sync-toggle-btn`, and `#sync-dropdown` after page load; assert the old `#sync-btn` is absent.
- **Primary button label**: assert `#sync-primary-btn` text is `"⟳ Sync New Data"`.
- **Dropdown toggle label**: assert `#sync-toggle-btn` text is `"▾"`.
- **Loading state disables both segments**: call `setLoading(true)`, assert both buttons have `disabled` attribute and primary shows `"⟳ Syncing…"`.
- **Dropdown contents**: open dropdown, assert exactly 3 `[role="menuitem"]` elements with the correct labels in order.
- **Click outside closes dropdown**: open dropdown, simulate click on `document.body`, assert dropdown is hidden and no fetch was called.
- **Dropdown blocked during loading**: set loading, click toggle, assert dropdown remains hidden.
- **Mode → fetch body mapping**: for each of `delta`, `force`, `missing`, click the corresponding control and assert `fetch` was called with the correct JSON body.
- **Success path reloads data**: mock successful API response, assert `loadLabels` and `loadMessages` were called.
- **Loading overlay labels**: for each mode, assert the overlay label text matches the expected string.
- **ARIA roles**: assert `#sync-dropdown` has `role="menu"` and all items have `role="menuitem"`.
- **Keyboard navigation**: open dropdown, press `ArrowDown`, assert focus moves to first item; press `ArrowDown` again, assert focus moves to second item; press `Escape`, assert dropdown closes and focus returns to toggle.
- **Backend: mode absent defaults to missing**: POST `{}` to `/api/sync`, assert subprocess called without `--delta` or `--force`.
- **Backend: timeout preserved**: assert `timeout=300` is present in subprocess call for all modes.

### Property-Based Tests

Property-based testing is applicable here because several behaviors are universal across input ranges (mode values, error strings, state sequences). The project uses Python for the backend; [Hypothesis](https://hypothesis.readthedocs.io/) is the recommended library for backend properties. For frontend properties, [fast-check](https://fast-check.dev/) is recommended.

Each property test runs a minimum of **100 iterations**.

**Property 1 — Loading round-trip** *(fast-check, frontend)*
- Feature: sync-button-dropdown, Property 1: loading state is a round-trip for split button segments
- Generate: arbitrary initial label text for the primary button
- Assert: `setLoading(true)` then `setLoading(false)` restores `disabled=false` and original label

**Property 2 — Backend mode routing** *(Hypothesis, backend)*
- Feature: sync-button-dropdown, Property 2: backend mode routing correctness
- Generate: `mode` drawn from `sampled_from(['delta', 'force', 'missing'])`, `data_dir` drawn from `text()`
- Assert: subprocess command contains exactly the expected flags for the given mode

**Property 3 — Invalid mode rejection** *(Hypothesis, backend)*
- Feature: sync-button-dropdown, Property 3: invalid mode values are rejected
- Generate: `mode` drawn from `text()` filtered to exclude `{'delta', 'force', 'missing'}`
- Assert: response status is 400 and `error` field is non-empty

**Property 4 — Error message surfacing** *(fast-check, frontend)*
- Feature: sync-button-dropdown, Property 4: error messages are surfaced to the UI
- Generate: arbitrary non-empty error string
- Assert: after a failed sync response containing that string, `state.error` equals the string and the error banner displays it

**Property 5 — Loading overlay label** *(fast-check or Hypothesis)*
- Feature: sync-button-dropdown, Property 5: loading overlay label matches sync mode
- Generate: `mode` drawn from `sampled_from(['delta', 'force', 'missing'])`
- Assert: the label passed to `setLoading` matches the expected mode-specific string

**Property 6 — `aria-expanded` accuracy** *(fast-check, frontend)*
- Feature: sync-button-dropdown, Property 6: aria-expanded accurately reflects dropdown state
- Generate: arbitrary sequence of open/close toggle operations
- Assert: after each operation, `aria-expanded` equals `"true"` iff the dropdown is visible

**Property 7 — Keyboard Enter triggers correct mode** *(fast-check, frontend)*
- Feature: sync-button-dropdown, Property 7: keyboard Enter on any menu item triggers its sync mode
- Generate: item index drawn from `integer({min: 0, max: 2})`
- Assert: pressing Enter on item at that index calls `runSync` with the correct mode for that index and closes the dropdown
