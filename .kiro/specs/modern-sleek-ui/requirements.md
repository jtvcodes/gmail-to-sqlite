# Requirements Document

## Introduction

This feature redesigns the Gmail Web Viewer's user interface from its current minimal, utility-first style into a modern, Notion-inspired layout with a full visual overhaul, structural improvements, and built-in dark/light mode support. The redesign targets improved readability, spatial hierarchy, and discoverability while preserving all existing functionality (sync, filtering, message list, message detail, attachments). UX improvements — such as a collapsible sidebar, command palette, keyboard-first navigation, and contextual inline previews — are included as first-class requirements.

---

## Glossary

- **App**: The Gmail Web Viewer single-page application.
- **Theme**: The active color scheme — either `light` or `dark`.
- **Theme_Manager**: The subsystem responsible for applying, persisting, and toggling the active Theme.
- **Sidebar**: The collapsible left-hand navigation panel containing label filters and quick-access controls.
- **Command_Palette**: The keyboard-triggered overlay that allows the user to search and execute any App action by typing.
- **Message_List**: The scrollable panel displaying the paginated list of email messages.
- **Message_Detail**: The panel (slide-in drawer or split-pane) displaying the full content of a selected message.
- **Filter_Bar**: The control strip containing the search input, label selector, and read/deleted toggles.
- **Sync_Control**: The split-button control that triggers sync operations.
- **Toast**: A transient, non-blocking notification that appears at the bottom of the viewport.
- **Loading_Overlay**: The full-screen semi-transparent overlay shown during sync operations.
- **Design_Token**: A named CSS custom property (variable) representing a color, spacing, radius, or typography value.
- **WCAG_AA**: Web Content Accessibility Guidelines 2.1 Level AA contrast and interaction requirements.
- **Attachment_Popover**: The dropdown/popover panel that lists all attachments for a message, triggered by clicking the attachment icon in a Message_List row.
- **Attachment_Preview_Modal**: The modal overlay that displays a single attachment, supporting inline rendering for supported file types and a fallback view for unsupported types.
- **Supported_Preview_Type**: A file type for which the Attachment_Preview_Modal renders an inline preview — currently images (JPEG, PNG, GIF, WebP, SVG) and PDFs.
- **Reading_Pane**: The inline preview panel that displays message content alongside or below the Message_List, visible when the Reading_Pane_Mode is `right` or `below`.
- **Reading_Pane_Mode**: The user-selected layout configuration for the Reading_Pane — one of `right` (pane to the right of the Message_List), `below` (pane below the Message_List), or `none` (no pane; Message_List occupies the full content area).

---

## Requirements

### Requirement 1: Design Token System

**User Story:** As a developer, I want all visual values defined as CSS custom properties, so that theming and future style changes require edits in one place.

#### Acceptance Criteria

1. THE App SHALL define all colors, spacing scale, border radii, font sizes, font weights, and shadow values as Design_Tokens on the `:root` selector.
2. THE App SHALL define a `[data-theme="dark"]` selector that overrides all color Design_Tokens with their dark-mode equivalents.
3. WHEN a Design_Token is updated, THE App SHALL reflect the change across every component that references that token without requiring per-component CSS edits.
4. THE App SHALL use no hard-coded color, spacing, or typography values in component CSS rules — all such values SHALL reference a Design_Token.

---

### Requirement 2: Light / Dark Mode Toggle

**User Story:** As a user, I want to switch between light and dark mode, so that I can use the App comfortably in different lighting conditions.

#### Acceptance Criteria

1. THE App SHALL render a theme toggle control visible in the header at all times.
2. WHEN the user activates the theme toggle, THE Theme_Manager SHALL switch the active Theme between `light` and `dark`.
3. WHEN the Theme changes, THE Theme_Manager SHALL apply the new Theme by setting `data-theme` on the `<html>` element within 50 ms.
4. THE Theme_Manager SHALL persist the user's Theme preference to `localStorage` under the key `"gmailviewer-theme"`.
5. WHEN the App initialises, THE Theme_Manager SHALL restore the persisted Theme preference; IF no preference is stored, THE Theme_Manager SHALL apply the Theme that matches the OS `prefers-color-scheme` media query.
6. WHILE dark Theme is active, THE App SHALL maintain WCAG_AA contrast ratios (minimum 4.5:1 for normal text, 3:1 for large text) for all visible text and interactive elements.
7. WHILE light Theme is active, THE App SHALL maintain WCAG_AA contrast ratios for all visible text and interactive elements.

---

### Requirement 3: Collapsible Sidebar Navigation

**User Story:** As a user, I want a sidebar that shows my labels and lets me filter messages, so that I can navigate my inbox without using the top filter bar.

#### Acceptance Criteria

1. THE App SHALL render a Sidebar on the left side of the main content area containing: an "All Mail" entry, a list of all available labels, and a read/unread filter toggle.
2. WHEN the user clicks a label in the Sidebar, THE Message_List SHALL reload showing only messages with that label, and the active label SHALL be visually highlighted.
3. THE App SHALL render a collapse/expand toggle button on the Sidebar.
4. WHEN the user activates the Sidebar collapse toggle, THE Sidebar SHALL animate to a collapsed icon-only state within 200 ms.
5. WHEN the Sidebar is collapsed, THE App SHALL display only icon representations of each navigation item with a tooltip on hover.
6. THE Theme_Manager SHALL persist the Sidebar collapsed/expanded state to `localStorage` under the key `"gmailviewer-sidebar-collapsed"`.
7. WHEN the App initialises, THE App SHALL restore the persisted Sidebar state.
8. WHILE the viewport width is less than 768 px, THE App SHALL render the Sidebar as a hidden off-canvas drawer that overlays the content rather than pushing it.

---

### Requirement 4: Redesigned Header

**User Story:** As a user, I want a clean, minimal header that keeps key controls accessible without visual clutter.

#### Acceptance Criteria

1. THE App SHALL render a header containing: the application logo/name on the left, the Sync_Control in the centre-right area, the theme toggle, and a keyboard shortcut hint for the Command_Palette.
2. THE App SHALL apply a subtle bottom border and a backdrop-blur effect to the header so it remains visually distinct when content scrolls beneath it.
3. WHEN the page is scrolled more than 0 px, THE App SHALL add a drop-shadow to the header to reinforce the layering.
4. THE App SHALL render the header at a fixed position so it remains visible during scroll.

---

### Requirement 5: Redesigned Message List

**User Story:** As a user, I want the message list to be easy to scan, so that I can quickly identify important messages.

#### Acceptance Criteria

1. THE Message_List SHALL render each message as a card row with clearly separated sender, subject, date, and status columns.
2. WHEN a message is unread, THE Message_List SHALL render the sender name and subject in a heavier font weight and apply a left-side accent border using the primary Design_Token color.
3. WHEN a message is deleted, THE Message_List SHALL render the row with a strikethrough and reduced opacity.
4. WHEN the user hovers over a message row, THE Message_List SHALL apply a background highlight transition within 120 ms.
5. THE Message_List SHALL display an attachment icon on rows where `has_attachments` is true, positioned after the subject text; WHEN the user clicks the attachment icon, THE Message_List SHALL open an Attachment_Popover listing all attachments for that message.
6. WHEN the Message_List contains zero messages, THE Message_List SHALL display a centred empty-state illustration and the text "No messages found."
7. THE Message_List SHALL render pagination controls below the list showing current page, total pages, and Previous/Next buttons.
8. WHEN the user clicks a sortable column header, THE Message_List SHALL toggle the sort direction and re-fetch messages.

---

### Requirement 6: Inline Message Preview (Reading Pane)

**User Story:** As a user, I want to choose how message previews are displayed alongside the message list, so that I can triage messages faster using a layout that suits my workflow.

#### Acceptance Criteria

1. THE App SHALL support three Reading_Pane_Mode values: `right` (Reading_Pane displayed to the right of the Message_List), `below` (Reading_Pane displayed below the Message_List), and `none` (no Reading_Pane; the Message_List occupies the full content area).
2. THE App SHALL render a Reading_Pane_Mode selector control accessible from the header or settings area, allowing the user to switch between `right`, `below`, and `none`.
3. THE App SHALL persist the user's Reading_Pane_Mode preference to `localStorage` under the key `"gmailviewer-reading-pane"`.
4. WHEN the App initialises, THE App SHALL restore the persisted Reading_Pane_Mode preference; IF no preference is stored, THE App SHALL default to `right` mode.
5. WHEN the Reading_Pane_Mode is `none` and the user single-clicks a message row, THE App SHALL open the message in a full Message_Detail window.
6. WHEN the Reading_Pane_Mode is `right` or `below` and the user single-clicks a message row, THE Reading_Pane SHALL load and display the content of that message.
7. WHEN the Reading_Pane_Mode is `right` or `below` and the user double-clicks a message row, THE App SHALL open the message in a full Message_Detail window.
8. WHILE the Reading_Pane_Mode is `right`, THE Message_List SHALL resize to occupy the remaining horizontal space beside the Reading_Pane.
9. WHILE the Reading_Pane_Mode is `below`, THE Message_List SHALL occupy the full width of the content area above the Reading_Pane.
10. WHEN the Reading_Pane displays a message, THE Reading_Pane SHALL render the message subject, sender, date, labels, body, and attachments.
11. WHEN the user presses `Escape` while a Message_Detail window is open, THE App SHALL close the Message_Detail and return focus to the previously selected message row.
12. WHILE the Reading_Pane_Mode is `right` and the viewport width is less than 900 px, THE App SHALL fall back to `below` mode automatically.
13. WHILE the Reading_Pane_Mode is `below` and the viewport width is less than 600 px, THE App SHALL fall back to `none` mode automatically.

---

### Requirement 7: Command Palette

**User Story:** As a power user, I want a keyboard-triggered command palette, so that I can perform any action without reaching for the mouse.

#### Acceptance Criteria

1. WHEN the user presses `Cmd+K` (macOS) or `Ctrl+K` (Windows/Linux), THE Command_Palette SHALL open as a centred modal overlay.
2. THE Command_Palette SHALL display a text input field that is focused immediately upon opening.
3. WHEN the user types in the Command_Palette input, THE Command_Palette SHALL filter and display matching actions in real time with no more than 100 ms latency.
4. THE Command_Palette SHALL include the following built-in actions: "Sync New Data", "Force Sync All", "Sync Missing", "Toggle Dark Mode", "Collapse Sidebar", "Go to page N".
5. WHEN the user selects an action from the Command_Palette (via Enter key or mouse click), THE Command_Palette SHALL execute the action and close.
6. WHEN the user presses `Escape` while the Command_Palette is open, THE Command_Palette SHALL close without executing any action.
7. WHEN the Command_Palette is open, THE App SHALL trap focus within the palette and prevent interaction with background content.
8. THE Command_Palette SHALL support keyboard navigation: `ArrowDown` and `ArrowUp` move focus between results; `Enter` executes the focused result.

---

### Requirement 8: Toast Notification System

**User Story:** As a user, I want brief, non-blocking feedback after actions, so that I know whether an operation succeeded or failed without a disruptive overlay.

#### Acceptance Criteria

1. WHEN a sync operation completes successfully, THE App SHALL display a success Toast with the text "Sync complete" for 3000 ms then dismiss it automatically.
2. WHEN a sync operation fails, THE App SHALL display an error Toast with a descriptive message that persists until the user dismisses it manually.
3. THE App SHALL render Toasts in the bottom-right corner of the viewport, stacked vertically with 8 px gap between them.
4. WHEN multiple Toasts are queued, THE App SHALL display them in FIFO order, stacking up to 3 visible at once.
5. WHEN the user clicks the dismiss button on a Toast, THE App SHALL remove that Toast with a fade-out animation within 200 ms.
6. THE App SHALL render success Toasts with a green accent and error Toasts with a red accent, using Design_Tokens for both colors.
7. WHILE dark Theme is active, THE App SHALL render Toasts using dark-mode Design_Token colors.

---

### Requirement 9: Keyboard Shortcut System

**User Story:** As a power user, I want keyboard shortcuts for common actions, so that I can navigate and operate the App without a mouse.

#### Acceptance Criteria

1. THE App SHALL support the following global keyboard shortcuts:
   - `Cmd/Ctrl+K`: open Command_Palette
   - `J`: select next message in Message_List
   - `K`: select previous message in Message_List
   - `O` or `Enter`: open selected message in Message_Detail
   - `Escape`: close Message_Detail or Command_Palette
   - `R`: trigger delta sync (equivalent to clicking "Sync New Data")
2. WHEN a keyboard shortcut is triggered while a text input is focused, THE App SHALL NOT execute the shortcut (except `Escape` and `Cmd/Ctrl+K`).
3. THE App SHALL render a keyboard shortcut reference accessible via the `?` key that lists all available shortcuts in a modal overlay.

---

### Requirement 10: Responsive Layout

**User Story:** As a user, I want the App to be usable on different screen sizes, so that I can access it from a laptop or a large monitor.

#### Acceptance Criteria

1. WHILE the viewport width is 1200 px or greater, THE App SHALL render the Sidebar expanded alongside the Message_List.
2. WHILE the viewport width is between 768 px and 1199 px, THE App SHALL render the Sidebar in collapsed icon-only mode by default.
3. WHILE the viewport width is less than 768 px, THE App SHALL hide the Sidebar and render a hamburger menu button in the header that opens the Sidebar as an off-canvas overlay.
4. THE App SHALL use fluid widths and a CSS grid or flexbox layout so that no horizontal scrollbar appears at any viewport width of 320 px or greater.
5. WHEN the viewport is resized, THE App SHALL reflow the layout within one animation frame without requiring a page reload.

---

### Requirement 11: Accessibility

**User Story:** As a user relying on assistive technology, I want the App to be navigable by keyboard and screen reader, so that I can use it without a mouse.

#### Acceptance Criteria

1. THE App SHALL assign correct ARIA roles, labels, and live regions to all interactive components: Sidebar, Message_List rows, Message_Detail, Command_Palette, Sync_Control, and Toasts.
2. THE App SHALL maintain a logical tab order across all interactive elements.
3. WHEN a modal or overlay (Command_Palette, Message_Detail in drawer mode, attachment preview) opens, THE App SHALL trap focus within it and restore focus to the triggering element on close.
4. THE App SHALL announce Toast notifications to screen readers via an `aria-live="polite"` region.
5. THE App SHALL provide visible focus indicators on all interactive elements that meet WCAG_AA contrast requirements.
6. THE App SHALL not rely solely on color to convey information (e.g., unread status SHALL also use font weight; error state SHALL also use an icon).

---

### Requirement 12: Smooth Animations and Transitions

**User Story:** As a user, I want UI transitions to feel fluid and intentional, so that the App feels polished rather than abrupt.

#### Acceptance Criteria

1. THE App SHALL apply CSS transitions to: Sidebar collapse/expand, Message_Detail open/close, dropdown open/close, hover states on rows and buttons, and Toast appear/dismiss.
2. WHEN the user has enabled the OS `prefers-reduced-motion` setting, THE App SHALL disable or reduce all non-essential animations to a simple opacity fade of no more than 100 ms.
3. THE App SHALL use `transform` and `opacity` for animations rather than properties that trigger layout reflow (e.g., `width`, `height`, `top`, `left`), except where layout change is the intent.

---

### Requirement 13: Density / Layout Mode Selector

**User Story:** As a user, I want to choose between a compact and a cozy display mode, so that I can control how much information is visible at once based on my preference.

#### Acceptance Criteria

1. THE App SHALL support two density modes: `compact` and `cozy`.
2. THE App SHALL render a density mode toggle control accessible from the App settings area or header controls.
3. WHEN the user selects `compact` mode, THE App SHALL apply Design_Tokens that reduce row heights, decrease vertical padding, and decrease inter-element spacing in the Message_List and overall UI, allowing more messages to be visible simultaneously.
4. WHEN the user selects `cozy` mode, THE App SHALL apply Design_Tokens that increase row heights, increase vertical padding, and increase inter-element spacing in the Message_List and overall UI, providing more visual breathing room between elements.
5. THE App SHALL define all density-specific spacing values as Design_Tokens (e.g., `--density-row-height`, `--density-padding-y`, `--density-gap`) so that switching modes requires only a token override rather than per-component CSS edits.
6. THE App SHALL persist the user's density mode preference to `localStorage` under the key `"gmailviewer-density"`.
7. WHEN the App initialises, THE App SHALL restore the persisted density mode preference; IF no preference is stored, THE App SHALL default to `cozy` mode.
8. WHEN the density mode changes, THE App SHALL apply the new Design_Tokens within 50 ms without requiring a page reload.
9. WHILE dark Theme is active, THE App SHALL apply the selected density mode using the same Design_Tokens, ensuring density and theme operate independently.
10. WHILE light Theme is active, THE App SHALL apply the selected density mode using the same Design_Tokens, ensuring density and theme operate independently.

---

### Requirement 14: Attachment Preview

**User Story:** As a user, I want to browse and preview message attachments without leaving the message list, so that I can quickly inspect files without downloading them first.

#### Acceptance Criteria

1. WHEN the user clicks the attachment icon on a message row, THE Attachment_Popover SHALL open adjacent to the icon and display a list of all attachments for that message, each entry showing the filename, a file-type icon, and the file size.
2. WHEN the Attachment_Popover is open and the user clicks outside it or presses `Escape`, THE Attachment_Popover SHALL close without opening a preview.
3. WHEN the user clicks a single attachment entry in the Attachment_Popover, THE Attachment_Preview_Modal SHALL open displaying that attachment.
4. WHILE the attachment is a Supported_Preview_Type, THE Attachment_Preview_Modal SHALL render an inline preview of the file content (image rendered as `<img>`, PDF rendered in an embedded viewer).
5. WHILE the attachment is not a Supported_Preview_Type, THE Attachment_Preview_Modal SHALL display a file-type icon and the filename as a fallback view in place of an inline preview.
6. THE Attachment_Preview_Modal SHALL render the following action controls: a Download button that initiates a file download, a Print button that triggers the browser print dialog scoped to the attachment content, and a Close button that dismisses the modal.
7. WHEN the user presses `Escape` while the Attachment_Preview_Modal is open, THE Attachment_Preview_Modal SHALL close and return focus to the attachment icon that triggered the Attachment_Popover.
8. WHEN the Attachment_Preview_Modal opens, THE App SHALL trap focus within the modal until it is closed, in accordance with Requirement 11 AC 3.
9. THE Attachment_Preview_Modal SHALL be keyboard accessible: the Download, Print, and Close controls SHALL be reachable via `Tab` and activatable via `Enter` or `Space`.
10. THE Attachment_Popover and Attachment_Preview_Modal SHALL apply the active Theme's Design_Tokens so that both components render correctly in light and dark mode.
