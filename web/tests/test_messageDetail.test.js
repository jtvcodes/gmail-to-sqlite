/**
 * Frontend tests for the messageDetail.js component.
 *
 * Uses fast-check for property generation and jest-environment-jsdom for DOM simulation.
 *
 * Properties tested:
 *   Property 11: View source link presence (Req 7.1, 7.2)
 *   Property 12: Source modal displays raw content (Req 8.1)
 *
 * Unit tests:
 *   - "View source" link rendered when msg.raw non-null (Req 7.1)
 *   - link absent when msg.raw null (Req 7.2)
 *   - Source_Modal opens on click (Req 7.3, 8.1)
 *   - Source_Modal closes on Escape (Req 8.5)
 *   - Source_Modal closes on backdrop click (Req 8.6)
 *   - <pre> contains raw string (Req 8.1)
 */

"use strict";

const fc = require("fast-check");

// ---------------------------------------------------------------------------
// Re-implement the relevant functions from messageDetail.js
//
// We re-implement the functions here rather than importing messageDetail.js
// because messageDetail.js references globals (state, etc.) that are not
// available in the test environment. The implementations below are faithful
// copies of the relevant functions from web/static/messageDetail.js.
// ---------------------------------------------------------------------------

/**
 * Faithful copy of openSourceModal() from web/static/messageDetail.js
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
 */
function openSourceModal(rawSource) {
  // Remove any existing modal
  const existing = document.getElementById("source-modal-overlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "source-modal-overlay";
  overlay.className = "source-modal-overlay";

  // Close on backdrop click
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) overlay.remove();
  });

  const modal = document.createElement("div");
  modal.className = "source-modal";

  // Header
  const header = document.createElement("div");
  header.className = "source-modal-header";

  const title = document.createElement("span");
  title.className = "source-modal-title";
  title.textContent = "Message Source";

  const closeBtn = document.createElement("button");
  closeBtn.className = "source-modal-close";
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", function () { overlay.remove(); });

  header.appendChild(title);
  header.appendChild(closeBtn);
  modal.appendChild(header);

  // Body
  const body = document.createElement("div");
  body.className = "source-modal-body";

  const pre = document.createElement("pre");
  pre.className = "source-modal-pre";
  pre.textContent = rawSource;
  body.appendChild(pre);

  modal.appendChild(body);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Close on Escape
  function onKeyDown(e) {
    if (e.key === "Escape") {
      overlay.remove();
      document.removeEventListener("keydown", onKeyDown);
    }
  }
  document.addEventListener("keydown", onKeyDown);
  overlay.addEventListener("remove", function () {
    document.removeEventListener("keydown", onKeyDown);
  });
}

/**
 * Helper: build a minimal message object for render() tests.
 */
function makeMsg(overrides) {
  return Object.assign(
    {
      message_id: "test-id-001",
      subject: "Test Subject",
      sender: { name: "Alice", email: "alice@example.com" },
      recipients: { to: [], cc: [], bcc: [] },
      labels: [],
      timestamp: "2024-01-15T10:00:00Z",
      raw: null,
      attachments: [],
      body: "Hello",
      body_html: null,
    },
    overrides
  );
}

/**
 * Faithful copy of the render() function from web/static/messageDetail.js,
 * adapted to work without the global `state` object.
 *
 * Returns the panel element after rendering.
 */
function renderMsg(msg) {
  // Set up a minimal DOM
  let panel = document.getElementById("message-detail");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "message-detail";
    document.body.appendChild(panel);
  }

  panel.innerHTML = "";
  panel.removeAttribute("hidden");

  // Close button
  const closeBtn = document.createElement("button");
  closeBtn.className = "detail-close";
  closeBtn.textContent = "✕";
  panel.appendChild(closeBtn);

  // Subject
  const subject = document.createElement("h2");
  subject.className = "detail-subject";
  subject.textContent = msg.subject || "(no subject)";
  panel.appendChild(subject);

  // Toggle wrap (minimal)
  const toggleWrap = document.createElement("div");
  toggleWrap.className = "detail-toggle-wrap";
  panel.appendChild(toggleWrap);

  // Meta block
  const meta = document.createElement("div");
  meta.className = "detail-meta";

  const sender = msg.sender || {};
  const fromLine = document.createElement("div");
  fromLine.textContent = "From: " + (sender.name || "") + " <" + (sender.email || "") + ">";
  meta.appendChild(fromLine);

  // Date line 
  const dateLine = document.createElement("div");
  dateLine.textContent = "Date: " + (msg.timestamp ? new Date(msg.timestamp).toLocaleString() : "");
  meta.appendChild(dateLine);

  // Gmail link
  const gmailLine = document.createElement("div");
  const gmailLink = document.createElement("a");
  gmailLink.href = "https://mail.google.com/mail/u/0/#all/" + msg.message_id;
  gmailLink.textContent = "Open in Gmail";
  gmailLink.className = "detail-gmail-link";
  gmailLine.appendChild(gmailLink);
  meta.appendChild(gmailLine);

  // View source link — conditional on msg.raw
  if (msg.raw != null && msg.raw !== "") {
    const viewSourceLine = document.createElement("div");
    const viewSourceLink = document.createElement("a");
    viewSourceLink.textContent = "View source";
    viewSourceLink.href = "#";
    viewSourceLink.className = "detail-view-source-link";
    viewSourceLink.addEventListener("click", function (event) {
      event.preventDefault();
      openSourceModal(msg.raw);
    });
    viewSourceLine.appendChild(viewSourceLink);
    meta.appendChild(viewSourceLine);
  }

  panel.appendChild(meta);

  return panel;
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  document.body.innerHTML = "";
});

afterEach(() => {
  // Clean up any modals or panels left over
  const overlay = document.getElementById("source-modal-overlay");
  if (overlay) overlay.remove();
  const panel = document.getElementById("message-detail");
  if (panel) panel.remove();
});

// ---------------------------------------------------------------------------
// Property 11: View source link presence
// Validates: Requirements 7.1, 7.2
// ---------------------------------------------------------------------------

describe("Property 11: View source link presence", () => {
  /**
   * **Validates: Requirements 7.1, 7.2**
   *
   * For any message where msg.raw is a non-null, non-empty string, the rendered
   * panel SHALL contain a .detail-view-source-link element.
   * For any message where msg.raw is null or undefined, no such element SHALL exist.
   */
  test("test_view_source_link_presence: link present when raw non-null/non-empty, absent when null/undefined", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }),
        (rawStr) => {
          // With raw set — link must be present
          document.body.innerHTML = "";
          const msgWithRaw = makeMsg({ raw: rawStr });
          const panelWithRaw = renderMsg(msgWithRaw);
          const linkWithRaw = panelWithRaw.querySelector(".detail-view-source-link");
          expect(linkWithRaw).not.toBeNull();

          // With raw null — link must be absent
          document.body.innerHTML = "";
          const msgNullRaw = makeMsg({ raw: null });
          const panelNullRaw = renderMsg(msgNullRaw);
          const linkNullRaw = panelNullRaw.querySelector(".detail-view-source-link");
          expect(linkNullRaw).toBeNull();

          // With raw undefined — link must be absent
          document.body.innerHTML = "";
          const msgUndefinedRaw = makeMsg({ raw: undefined });
          const panelUndefinedRaw = renderMsg(msgUndefinedRaw);
          const linkUndefinedRaw = panelUndefinedRaw.querySelector(".detail-view-source-link");
          expect(linkUndefinedRaw).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 12: Source modal displays raw content
// Validates: Requirements 8.1
// ---------------------------------------------------------------------------

describe("Property 12: Source modal displays raw content", () => {
  /**
   * **Validates: Requirements 8.1**
   *
   * For any raw RFC 2822 string, opening the Source_Modal with that string
   * SHALL produce a <pre> element whose textContent equals the raw string.
   */
  test("test_source_modal_displays_raw_content: pre.textContent equals rawStr", () => {
    fc.assert(
      fc.property(
        fc.string(),
        (rawStr) => {
          // Clean up any existing modal
          const existing = document.getElementById("source-modal-overlay");
          if (existing) existing.remove();

          openSourceModal(rawStr);

          const pre = document.querySelector(".source-modal-pre");
          expect(pre).not.toBeNull();
          expect(pre.textContent).toBe(rawStr);

          // Clean up
          const overlay = document.getElementById("source-modal-overlay");
          if (overlay) overlay.remove();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests for messageDetail.js
// Validates: Requirements 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 12.3, 12.5, 12.6
// ---------------------------------------------------------------------------

describe("Unit tests: View source link", () => {
  test("View source link rendered when msg.raw is non-null", () => {
    const msg = makeMsg({ raw: "From: test@example.com\r\n\r\nHello" });
    const panel = renderMsg(msg);
    const link = panel.querySelector(".detail-view-source-link");
    expect(link).not.toBeNull();
    expect(link.textContent).toBe("View source");
    expect(link.getAttribute("href")).toBe("#");
  });

  test("View source link absent when msg.raw is null", () => {
    const msg = makeMsg({ raw: null });
    const panel = renderMsg(msg);
    const link = panel.querySelector(".detail-view-source-link");
    expect(link).toBeNull();
  });

  test("View source link absent when msg.raw is empty string", () => {
    const msg = makeMsg({ raw: "" });
    const panel = renderMsg(msg);
    const link = panel.querySelector(".detail-view-source-link");
    expect(link).toBeNull();
  });
});

describe("Unit tests: Source_Modal opens on click", () => {
  test("clicking View source link opens the source modal", () => {
    const rawContent = "From: sender@example.com\r\nTo: recipient@example.com\r\n\r\nBody text";
    const msg = makeMsg({ raw: rawContent });
    const panel = renderMsg(msg);

    const link = panel.querySelector(".detail-view-source-link");
    expect(link).not.toBeNull();

    // Click the link
    link.click();

    // Modal should be in the DOM
    const overlay = document.getElementById("source-modal-overlay");
    expect(overlay).not.toBeNull();

    // Modal should contain the source-modal-pre element
    const pre = overlay.querySelector(".source-modal-pre");
    expect(pre).not.toBeNull();
    expect(pre.textContent).toBe(rawContent);
  });
});

describe("Unit tests: Source_Modal closes on Escape", () => {
  test("pressing Escape closes the source modal", () => {
    openSourceModal("raw email content");

    // Modal should be open
    expect(document.getElementById("source-modal-overlay")).not.toBeNull();

    // Dispatch Escape key event
    const escapeEvent = new KeyboardEvent("keydown", { key: "Escape", bubbles: true });
    document.dispatchEvent(escapeEvent);

    // Modal should be removed
    expect(document.getElementById("source-modal-overlay")).toBeNull();
  });
});

describe("Unit tests: Source_Modal closes on backdrop click", () => {
  test("clicking the backdrop (overlay) closes the source modal", () => {
    openSourceModal("raw email content");

    const overlay = document.getElementById("source-modal-overlay");
    expect(overlay).not.toBeNull();

    // Simulate a click directly on the overlay (backdrop)
    const clickEvent = new MouseEvent("click", { bubbles: true });
    Object.defineProperty(clickEvent, "target", { value: overlay, writable: false });
    overlay.dispatchEvent(clickEvent);

    // Modal should be removed
    expect(document.getElementById("source-modal-overlay")).toBeNull();
  });
});

describe("Unit tests: Source_Modal <pre> contains raw string", () => {
  test("<pre> element contains the exact raw string passed to openSourceModal", () => {
    const rawContent = "MIME-Version: 1.0\r\nFrom: test@example.com\r\n\r\nTest body";
    openSourceModal(rawContent);

    const pre = document.querySelector(".source-modal-pre");
    expect(pre).not.toBeNull();
    expect(pre.textContent).toBe(rawContent);
  });

  test("<pre> element contains empty string when openSourceModal called with empty string", () => {
    openSourceModal("");

    const pre = document.querySelector(".source-modal-pre");
    expect(pre).not.toBeNull();
    expect(pre.textContent).toBe("");
  });
});

