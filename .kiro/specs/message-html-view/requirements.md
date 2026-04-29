# Requirements Document

## Introduction

The Gmail Web Viewer currently displays message bodies by auto-detecting whether the content is HTML or plain text from a single `body` field. The backend already stores and serves two distinct fields: `body_html` (the HTML version) and `body` (the plain-text version). This feature updates the message detail view to use `body_html` as the default rendering format when a message is opened, and adds a toggle button that lets the user switch to the plain-text view (`body`). The toggle persists for the lifetime of the open message panel and resets to HTML when a new message is opened.

## Glossary

- **Message_Detail**: The slide-in panel rendered by `messageDetail.js` that displays the full content of a selected email message.
- **HTML_View**: The rendering mode in which the message body is displayed using the `body_html` field, rendered inside a sandboxed iframe.
- **Plain_Text_View**: The rendering mode in which the message body is displayed using the `body` field, rendered as pre-formatted text inside a sandboxed iframe.
- **View_Toggle**: The button within the Message_Detail panel that switches between HTML_View and Plain_Text_View.
- **Active_View**: The currently selected rendering mode (HTML_View or Plain_Text_View) for the open message.
- **body_html**: The HTML-formatted body field returned by the `/api/messages/<message_id>` endpoint.
- **body**: The plain-text body field returned by the `/api/messages/<message_id>` endpoint.

## Requirements

### Requirement 1: Default HTML Rendering

**User Story:** As a user, I want messages to display in HTML format by default when I open them, so that I see the richly formatted version of the email as the sender intended.

#### Acceptance Criteria

1. WHEN a message is opened in the Message_Detail panel, THE Message_Detail SHALL set the Active_View to HTML_View.
2. WHEN the Active_View is HTML_View and `body_html` is non-empty, THE Message_Detail SHALL render the `body_html` field inside the sandboxed iframe.
3. WHEN the Active_View is HTML_View and `body_html` is empty or null, THE Message_Detail SHALL fall back to rendering the `body` field inside the sandboxed iframe.
4. WHEN a new message is opened while the Message_Detail panel is already visible, THE Message_Detail SHALL reset the Active_View to HTML_View.

### Requirement 2: Plain-Text Toggle

**User Story:** As a user, I want to switch to a plain-text view of a message, so that I can read the message without HTML formatting or styling.

#### Acceptance Criteria

1. THE Message_Detail SHALL display a View_Toggle button in the message detail panel whenever a message is open.
2. WHEN the Active_View is HTML_View, THE View_Toggle SHALL display the label "Plain text".
3. WHEN the Active_View is Plain_Text_View, THE View_Toggle SHALL display the label "HTML".
4. WHEN the user activates the View_Toggle while the Active_View is HTML_View, THE Message_Detail SHALL switch the Active_View to Plain_Text_View and re-render the iframe content using the `body` field.
5. WHEN the user activates the View_Toggle while the Active_View is Plain_Text_View, THE Message_Detail SHALL switch the Active_View to HTML_View and re-render the iframe content using the `body_html` field (or `body` if `body_html` is empty).
6. WHEN the Active_View is Plain_Text_View, THE Message_Detail SHALL render the `body` field as pre-formatted text with URL linkification inside the sandboxed iframe.

### Requirement 3: Toggle Availability

**User Story:** As a user, I want the toggle button to only appear when both HTML and plain-text content are available, so that I am not presented with a non-functional control.

#### Acceptance Criteria

1. WHEN a message has a non-empty `body_html` field AND a non-empty `body` field, THE Message_Detail SHALL display the View_Toggle button.
2. WHEN a message has an empty or null `body_html` field, THE Message_Detail SHALL hide the View_Toggle button and render the `body` field directly.
3. WHEN a message has an empty or null `body` field, THE Message_Detail SHALL hide the View_Toggle button and render the `body_html` field directly.

### Requirement 4: View Toggle Button Styling

**User Story:** As a user, I want the toggle button to be visually consistent with the rest of the message detail panel, so that the interface feels cohesive.

#### Acceptance Criteria

1. THE View_Toggle SHALL be positioned in the message detail header area, near the subject line or meta block, so that it is visible without scrolling.
2. THE View_Toggle SHALL use a visual style consistent with existing secondary action buttons in the application (border, background, font size, border-radius).
3. WHEN the Active_View is Plain_Text_View, THE View_Toggle SHALL have a distinct visual state (e.g., depressed or highlighted appearance) to indicate the non-default mode is active.

### Requirement 5: Iframe Re-render on Toggle

**User Story:** As a user, I want the message body to update immediately when I click the toggle, so that I do not need to reload the page or reopen the message.

#### Acceptance Criteria

1. WHEN the user activates the View_Toggle, THE Message_Detail SHALL update the iframe content in-place without closing and reopening the detail panel.
2. WHEN the iframe content is updated after a toggle, THE Message_Detail SHALL resize the iframe height to match the new content height.
3. WHEN the iframe content is updated after a toggle, THE Message_Detail SHALL preserve the scroll position of the Message_Detail panel at the top of the body section.
