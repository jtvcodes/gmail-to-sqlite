# Bugfix Requirements Document

## Introduction

When opening a message in the web viewer's detail panel, the TO, CC, and BCC fields display `[object Object]` instead of the recipient's name and email address. This happens because the frontend joins an array of recipient objects directly using `.join(", ")`, which coerces each object to its default string representation rather than formatting it as a human-readable address. The bug affects all messages that have recipients stored as structured objects.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a message with one or more TO recipients is opened in the detail view THEN the system displays `[object Object]` for each recipient instead of the formatted address

1.2 WHEN a message with one or more CC recipients is opened in the detail view THEN the system displays `[object Object]` for each recipient instead of the formatted address

1.3 WHEN a message with one or more BCC recipients is opened in the detail view THEN the system displays `[object Object]` for each recipient instead of the formatted address

### Expected Behavior (Correct)

2.1 WHEN a message with one or more TO recipients is opened in the detail view THEN the system SHALL display each recipient as a formatted address (e.g. `Name <email@example.com>` when a name is present, or `email@example.com` when no name is present)

2.2 WHEN a message with one or more CC recipients is opened in the detail view THEN the system SHALL display each recipient as a formatted address (e.g. `Name <email@example.com>` when a name is present, or `email@example.com` when no name is present)

2.3 WHEN a message with one or more BCC recipients is opened in the detail view THEN the system SHALL display each recipient as a formatted address (e.g. `Name <email@example.com>` when a name is present, or `email@example.com` when no name is present)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a message has no TO recipients THEN the system SHALL CONTINUE TO omit the TO line from the detail view

3.2 WHEN a message has no CC recipients THEN the system SHALL CONTINUE TO omit the CC line from the detail view

3.3 WHEN a message has no BCC recipients THEN the system SHALL CONTINUE TO omit the BCC line from the detail view

3.4 WHEN a message is opened in the detail view THEN the system SHALL CONTINUE TO display the From field correctly using the sender's name and email

3.5 WHEN a message is opened in the detail view THEN the system SHALL CONTINUE TO display the subject, date, labels, and body without change
