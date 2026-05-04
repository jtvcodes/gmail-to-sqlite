# Requirements Document

## Introduction

The current sync button in the Gmail Web Viewer header is a single button that triggers a full sync (skipping already-known messages). This feature replaces it with a split button: the primary action performs a fast delta sync (new messages only), while a dropdown arrow exposes two additional sync modes — a forced full re-sync and a missing-data sync. This gives users quick access to the most common operation while keeping the more expensive or specialised modes one click away.

## Glossary

- **Split_Button**: A UI control combining a primary action button and a dropdown toggle that reveals additional actions.
- **Dropdown_Menu**: The list of additional sync actions revealed when the Split_Button toggle is activated.
- **Sync_New_Data**: A delta sync that fetches only messages newer than the most recently indexed message (`main.py sync --delta`).
- **Sync_All_Forced**: A forced full re-sync that re-fetches and overwrites every message in Gmail (`main.py sync --force`).
- **Sync_Missing**: A full sync that fetches all Gmail message IDs not yet present in the local database, including messages with missing body HTML (`main.py sync` with no flags).
- **Sync_API**: The Flask backend endpoint at `POST /api/sync` that executes the sync subprocess.
- **UI**: The single-page application served from `web/static/`.
- **Loading_Overlay**: The full-screen semi-transparent overlay displayed while an async operation is in progress.

---

## Requirements

### Requirement 1: Split Button Rendering

**User Story:** As a user, I want the sync control to show a primary "Sync New Data" button alongside a dropdown toggle, so that I can trigger the most common sync with one click and access other modes without cluttering the header.

#### Acceptance Criteria

1. THE UI SHALL render the sync control as a Split_Button in the header, replacing the existing single sync button.
2. THE Split_Button SHALL display a primary action labelled "⟳ Sync New Data" on the left segment.
3. THE Split_Button SHALL display a dropdown toggle (chevron "▾") on the right segment, visually separated from the primary action.
4. WHILE a sync operation is in progress, THE Split_Button SHALL disable both the primary action segment and the dropdown toggle segment.
5. WHILE a sync operation is in progress, THE Split_Button SHALL display "⟳ Syncing…" as the primary segment label.
6. WHEN a sync operation completes or fails, THE Split_Button SHALL re-enable both segments and restore the original labels.

---

### Requirement 2: Dropdown Menu Contents

**User Story:** As a user, I want the dropdown to list all available sync modes with clear labels, so that I can choose the right sync operation for my situation.

#### Acceptance Criteria

1. WHEN the dropdown toggle is activated, THE Dropdown_Menu SHALL appear containing exactly three items in this order: "⟳ Sync New Data", "⟳ Sync All (Forced)", "⟳ Sync Missing".
2. THE Dropdown_Menu item "Sync New Data" SHALL be labelled "⟳ Sync New Data".
3. THE Dropdown_Menu item "Sync All (Forced)" SHALL be labelled "⟳ Sync All (Forced)".
4. THE Dropdown_Menu item "Sync Missing" SHALL be labelled "⟳ Sync Missing".
5. WHEN the user clicks outside the Dropdown_Menu without selecting an item, THE Dropdown_Menu SHALL close without triggering any sync operation.
6. WHEN a sync operation is in progress, THE Dropdown_Menu SHALL not open when the toggle is activated.

---

### Requirement 3: Sync New Data Action

**User Story:** As a user, I want clicking the primary button to sync only new messages, so that routine syncs are fast and do not re-process data I already have.

#### Acceptance Criteria

1. WHEN the primary segment of the Split_Button is clicked, THE Sync_API SHALL be called with mode `delta`.
2. WHEN the "Sync New Data" item in the Dropdown_Menu is selected, THE Sync_API SHALL be called with mode `delta`.
3. WHEN the Sync_API is called with mode `delta`, THE Sync_API SHALL execute `main.py sync --delta --data-dir <data_dir>`.
4. WHEN the Sync_API call with mode `delta` succeeds, THE UI SHALL reload the message list and label list to reflect newly synced data.
5. IF the Sync_API call with mode `delta` returns an error, THEN THE UI SHALL display the error message in the error banner.

---

### Requirement 4: Sync All (Forced) Action

**User Story:** As a user, I want to force a complete re-sync of all messages, so that I can recover from data corruption or ensure all message fields are up to date.

#### Acceptance Criteria

1. WHEN the "Sync All (Forced)" item in the Dropdown_Menu is selected, THE Sync_API SHALL be called with mode `force`.
2. WHEN the Sync_API is called with mode `force`, THE Sync_API SHALL execute `main.py sync --force --data-dir <data_dir>`.
3. WHEN the Sync_API call with mode `force` succeeds, THE UI SHALL reload the message list and label list to reflect the updated data.
4. IF the Sync_API call with mode `force` returns an error, THEN THE UI SHALL display the error message in the error banner.

---

### Requirement 5: Sync Missing Action

**User Story:** As a user, I want to sync only messages that are absent from the local database, so that I can fill gaps without re-downloading data I already have.

#### Acceptance Criteria

1. WHEN the "Sync Missing" item in the Dropdown_Menu is selected, THE Sync_API SHALL be called with mode `missing`.
2. WHEN the Sync_API is called with mode `missing`, THE Sync_API SHALL execute `main.py sync --data-dir <data_dir>` (no additional flags).
3. WHEN the Sync_API call with mode `missing` succeeds, THE UI SHALL reload the message list and label list to reflect newly synced data.
4. IF the Sync_API call with mode `missing` returns an error, THEN THE UI SHALL display the error message in the error banner.

---

### Requirement 6: Backend Sync Mode Routing

**User Story:** As a developer, I want the sync API endpoint to accept a mode parameter and route to the correct subprocess command, so that each sync action maps to the right backend behaviour.

#### Acceptance Criteria

1. THE Sync_API SHALL accept an optional `mode` field in the POST request body (JSON), with accepted values `delta`, `force`, and `missing`.
2. WHEN the `mode` field is absent or set to `missing`, THE Sync_API SHALL execute `main.py sync --data-dir <data_dir>` with no additional flags.
3. WHEN the `mode` field is `delta`, THE Sync_API SHALL execute `main.py sync --delta --data-dir <data_dir>`.
4. WHEN the `mode` field is `force`, THE Sync_API SHALL execute `main.py sync --force --data-dir <data_dir>`.
5. IF an unrecognised `mode` value is supplied, THEN THE Sync_API SHALL return HTTP 400 with a descriptive error message.
6. THE Sync_API SHALL preserve all existing timeout, error-handling, and output-capture behaviour for all modes.

---

### Requirement 7: Loading Overlay Labelling

**User Story:** As a user, I want the loading overlay to show a label that reflects which sync mode is running, so that I know what operation is in progress.

#### Acceptance Criteria

1. WHEN a Sync_New_Data operation is in progress, THE Loading_Overlay SHALL display the label "Syncing new messages…".
2. WHEN a Sync_All_Forced operation is in progress, THE Loading_Overlay SHALL display the label "Force-syncing all messages…".
3. WHEN a Sync_Missing operation is in progress, THE Loading_Overlay SHALL display the label "Syncing missing messages…".

---

### Requirement 8: Accessibility

**User Story:** As a user relying on keyboard navigation or assistive technology, I want the split button and dropdown to be fully operable without a mouse, so that the sync controls are accessible.

#### Acceptance Criteria

1. THE Split_Button primary segment SHALL be focusable and activatable via the keyboard Enter and Space keys.
2. THE Split_Button dropdown toggle SHALL be focusable and activatable via the keyboard Enter and Space keys.
3. WHEN the Dropdown_Menu is open, THE UI SHALL allow keyboard navigation between menu items using the ArrowUp and ArrowDown keys.
4. WHEN the Dropdown_Menu is open and the Escape key is pressed, THE Dropdown_Menu SHALL close and return focus to the dropdown toggle.
5. WHEN a Dropdown_Menu item has focus and the Enter key is pressed, THE UI SHALL trigger the corresponding sync action and close the Dropdown_Menu.
6. THE Split_Button dropdown toggle SHALL carry an `aria-haspopup="true"` attribute and an `aria-expanded` attribute reflecting the open/closed state of the Dropdown_Menu.
7. THE Dropdown_Menu SHALL carry `role="menu"` and each item SHALL carry `role="menuitem"`.
