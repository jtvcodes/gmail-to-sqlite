// Message detail component for the Arkchive SPA
// Renders the detail panel into #message-detail.

let activeView = "html";

function formatRecipient(r) {
  if (r && typeof r === 'object') {
    return r.name ? r.name + ' <' + r.email + '>' : (r.email || '');
  }
  return String(r);
}

function render() {
  activeView = "html";

  const overlay = document.getElementById("message-detail-overlay");
  const panel = document.getElementById("message-detail");

  if (!state.selectedMessage) {
    if (overlay) overlay.setAttribute("hidden", "");
    return;
  }

  const msg = state.selectedMessage;
  panel.innerHTML = "";
  if (overlay) {
    overlay.removeAttribute("hidden");

    // Close on backdrop click (click on overlay but not the modal card)
    overlay.onclick = function (e) {
      if (e.target === overlay) {
        state.selectedMessage = null;
        overlay.setAttribute("hidden", "");
        state.onMessageClose();
      }
    };
  }

  // ── Sticky close bar ──────────────────────────────────────────────────────
  const closeBar = document.createElement("div");
  closeBar.className = "detail-close-bar";

  const closeBtn = document.createElement("button");
  closeBtn.className = "detail-close";
  closeBtn.setAttribute("aria-label", "Close message detail");
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", function () {
    state.selectedMessage = null;
    const overlay = document.getElementById("message-detail-overlay");
    if (overlay) overlay.setAttribute("hidden", "");
    state.onMessageClose();
  });
  closeBar.appendChild(closeBtn);
  panel.appendChild(closeBar);

  // ── Scrollable content area ───────────────────────────────────────────────
  const content = document.createElement("div");
  content.className = "detail-content";
  panel.appendChild(content);

  // Subject
  const subject = document.createElement("h2");
  subject.className = "detail-subject";
  subject.textContent = msg.subject || "(no subject)";
  content.appendChild(subject);

  // Create iframe early so toggle button can reference it
  const bodyDiv = document.createElement("div");
  bodyDiv.className = "detail-body";
  const iframe = document.createElement("iframe");
  iframe.className = "detail-body-frame";
  iframe.setAttribute("title", "Message body");
  bodyDiv.appendChild(iframe);

  // Toggle button — placed right after subject, before meta
  const toggleWrap = document.createElement("div");
  toggleWrap.className = "detail-toggle-wrap";
  const toggleBtn = buildToggleButton(msg, iframe, bodyDiv);
  if (toggleBtn !== null) {
    toggleWrap.appendChild(toggleBtn);
  }
  content.appendChild(toggleWrap);

  // Meta block
  const meta = document.createElement("div");
  meta.className = "detail-meta";

  const sender = msg.sender || {};
  const fromLine = document.createElement("div");
  fromLine.textContent = "From: " + (sender.name || "") + " <" + (sender.email || "") + ">";
  meta.appendChild(fromLine);

  const recipients = msg.recipients || {};

  if (recipients.to && recipients.to.length > 0) {
    const toLine = document.createElement("div");
    toLine.textContent = "To: " + recipients.to.map(formatRecipient).join(", ");
    meta.appendChild(toLine);
  }

  if (recipients.cc && recipients.cc.length > 0) {
    const ccLine = document.createElement("div");
    ccLine.textContent = "Cc: " + recipients.cc.map(formatRecipient).join(", ");
    meta.appendChild(ccLine);
  }

  if (recipients.bcc && recipients.bcc.length > 0) {
    const bccLine = document.createElement("div");
    bccLine.textContent = "Bcc: " + recipients.bcc.map(formatRecipient).join(", ");
    meta.appendChild(bccLine);
  }

  const dateLine = document.createElement("div");
  if (msg.received_date != null) {
    dateLine.textContent = "Received: " + new Date(msg.received_date).toLocaleString();
  } else {
    dateLine.textContent = "Date: " + (msg.timestamp ? new Date(msg.timestamp).toLocaleString() : "");
  }
  meta.appendChild(dateLine);

  const idLine = document.createElement("div");
  idLine.className = "detail-message-id";
  idLine.textContent = "ID: " + msg.message_id;
  idLine.title = "Message ID";
  meta.appendChild(idLine);

  // Gmail link
  const gmailLine = document.createElement("div");
  const gmailLink = document.createElement("a");
  gmailLink.href = "https://mail.google.com/mail/u/0/#all/" + msg.message_id;
  gmailLink.textContent = "Open in Gmail";
  gmailLink.target = "_blank";
  gmailLink.rel = "noopener noreferrer";
  gmailLink.className = "detail-gmail-link";
  gmailLine.appendChild(gmailLink);
  meta.appendChild(gmailLine);

  // View source link
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

  content.appendChild(meta);

  // Labels
  const labelsDiv = document.createElement("div");
  labelsDiv.className = "detail-labels";
  (msg.labels || []).forEach(function (label) {
    const span = document.createElement("span");
    span.className = "detail-label";
    span.textContent = label;
    labelsDiv.appendChild(span);
  });
  content.appendChild(labelsDiv);

  // Attachments section
  const attachments = msg.attachments || [];
  if (attachments.length > 0) {
    const attachDiv = document.createElement("div");
    attachDiv.className = "detail-attachments";

    // Stamp message_id on each attachment so the preview modal can build URLs
    const taggedAttachments = attachments.map(function (a) {
      return Object.assign({}, a, { _messageId: msg.message_id });
    });

    taggedAttachments.forEach(function (att, i) {
      // Use attachment_id-based URL when available, fall back to filename-based URL
      const dataUrl = att.attachment_id
        ? "/api/messages/" + msg.message_id + "/attachments/" + att.attachment_id + "/data"
        : "/api/messages/" + msg.message_id + "/attachments/by-filename/" + encodeURIComponent(att.filename) + "/data";
      const previewable = isPreviewable(att.mime_type);

      const item = document.createElement("div");
      item.className = "detail-attachment-item";
      item.style.cursor = "pointer";

      const icon = document.createElement("span");
      icon.className = "detail-attachment-icon";
      icon.textContent = attachmentIcon(att.mime_type);

      const info = document.createElement("span");
      info.className = "detail-attachment-info";

      const name = document.createElement("span");
      name.className = "detail-attachment-name";
      name.textContent = att.filename || "attachment";

      const metaSpan = document.createElement("span");
      metaSpan.className = "detail-attachment-meta";
      const kb = att.size ? Math.ceil(att.size / 1024) : 0;
      metaSpan.textContent = att.mime_type + (kb ? " · " + kb + " KB" : "") + (previewable ? " · click to preview" : " · click to download");

      info.appendChild(name);
      info.appendChild(metaSpan);
      item.appendChild(icon);
      item.appendChild(info);

      item.addEventListener("click", function () {
        if (previewable) {
          openAttachmentPreview(att, dataUrl, taggedAttachments, i);
        } else {
          const a = document.createElement("a");
          a.href = dataUrl;
          a.download = att.filename || "attachment";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        }
      });

      attachDiv.appendChild(item);
    });

    content.appendChild(attachDiv);
  }

  // Body — append the already-created bodyDiv and render content
  content.appendChild(bodyDiv);

  // Write content after appending so contentDocument is available
  renderBody(iframe, msg, activeView);
}

/**
 * renderBody(iframe, msg, view)
 *
 * Writes the appropriate message body content into the given sandboxed iframe.
 *
 * - view === "html": uses msg.body_html if non-empty, falls back to msg.body.
 * - view === "text": uses msg.body, wrapped in <pre> with HTML-escaping and
 *   URL linkification.
 *
 * After writing, triggers the iframe height resize via the load event and a
 * setTimeout fallback.
 *
 * Requirements: 1.2, 1.3, 2.4, 2.5, 2.6, 5.2
 */
function renderBody(iframe, msg, view) {
  let htmlContent;

  if (view === "text") {
    // Plain-text view: escape HTML, linkify URLs, wrap in <pre>
    const rawBody = msg.body || "";
    const escaped = rawBody
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const linkified = escaped.replace(
      /(https?:\/\/[^\s]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    htmlContent = `<pre style="white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:14px;line-height:1.6;margin:0">${linkified}</pre>`;
  } else {
    // HTML view: prefer body_html; if absent, render body as pre-formatted text
    const hasHtml = msg.body_html != null && msg.body_html !== "";
    if (hasHtml) {
      htmlContent = msg.body_html;
    } else {
      const rawBody = msg.body || "";
      const escaped = rawBody
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      const linkified = escaped.replace(
        /(https?:\/\/[^\s]+)/g,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
      );
      htmlContent = `<pre style="white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:14px;line-height:1.6;margin:0">${linkified}</pre>`;
    }
  }

  const doc = iframe.contentDocument || iframe.contentWindow.document;
  doc.open();
  doc.write(`<!DOCTYPE html><html><head><meta charset="UTF-8">
    <meta name="referrer" content="no-referrer">
    <style>
      body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; color: #333; }
      a { color: #1a73e8; }
      img { max-width: 100%; }
    </style>
  </head><body>${htmlContent}</body></html>`);
  doc.close();

  // Auto-resize iframe to content height
  iframe.addEventListener("load", function () {
    iframe.style.height = iframe.contentDocument.body.scrollHeight + "px";
  });
  // Fallback resize after a short delay
  setTimeout(function () {
    if (iframe.contentDocument) {
      iframe.style.height = iframe.contentDocument.body.scrollHeight + "px";
    }
  }, 100);
}

/**
 * buildToggleButton(msg, iframe, bodyDiv)
 *
 * Creates and returns a View_Toggle <button> element when both body_html and
 * body are non-empty, or returns null when only one (or neither) field is
 * available.
 *
 * Button behaviour:
 * - CSS class `view-toggle-btn` is always present.
 * - CSS class `view-toggle-btn--active` is added when activeView === "text".
 * - Label is "Plain text" when activeView === "html", "HTML" when "text".
 * - Click handler flips activeView, calls renderBody(), and updates the
 *   button label and active class in-place.
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 4.3, 5.1
 */
function buildToggleButton(msg, iframe, bodyDiv) {
  // Build a toggle switch: label "Plain text" with on/off switch
  const wrap = document.createElement("label");
  wrap.className = "view-toggle-switch";
  wrap.title = "Switch between HTML and plain text view";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = activeView === "html";

  const track = document.createElement("span");
  track.className = "view-toggle-track";

  const labelText = document.createElement("span");
  labelText.className = "view-toggle-label";
  labelText.textContent = "HTML";

  wrap.appendChild(checkbox);
  wrap.appendChild(track);
  wrap.appendChild(labelText);

  checkbox.addEventListener("change", function () {
    activeView = checkbox.checked ? "html" : "text";
    renderBody(iframe, msg, activeView);
  });

  return wrap;
}

/**
 * Returns true for MIME types the browser can preview natively.
 */
function isPreviewable(mimeType) {
  if (!mimeType) return false;
  if (mimeType.startsWith("image/")) return true;
  const previewable = [
    "application/pdf",
    "text/plain",
    "text/csv",
    "text/html",
  ];
  return previewable.includes(mimeType);
}

/**
 * Returns an appropriate emoji icon for a given MIME type.
 */
function attachmentIcon(mimeType) {
  if (!mimeType) return "📎";
  if (mimeType.startsWith("image/")) return "🖼️";
  if (mimeType === "application/pdf") return "📄";
  if (mimeType.startsWith("text/")) return "📝";
  if (mimeType.includes("zip") || mimeType.includes("compressed")) return "🗜️";
  if (mimeType.includes("spreadsheet") || mimeType === "text/csv") return "📊";
  if (mimeType.includes("word") || mimeType.includes("document")) return "📝";
  return "📎";
}

/**
 * Opens a modal overlay to preview a browser-compatible attachment.
 * Pass allAttachments (array) and currentIndex to enable prev/next navigation.
 * Falls back to single-attachment mode when allAttachments is omitted.
 */
function openAttachmentPreview(att, dataUrl, allAttachments, currentIndex) {
  // Normalise — support single-attachment calls from older code paths
  const list = allAttachments && allAttachments.length > 0 ? allAttachments : [att];
  let idx = (currentIndex !== undefined && currentIndex >= 0) ? currentIndex : 0;

  // Remember the element that triggered the popover so we can restore focus on close
  const triggerElement = document.activeElement || null;

  function attDataUrl(a) {
    return a.attachment_id
      ? "/api/messages/" + (a._messageId || att._messageId || "") + "/attachments/" + a.attachment_id + "/data"
      : "/api/messages/" + (a._messageId || att._messageId || "") + "/attachments/by-filename/" + encodeURIComponent(a.filename) + "/data";
  }

  // Remove any existing modal
  const existing = document.getElementById("attachment-preview-modal");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "attachment-preview-modal";
  overlay.className = "attachment-preview-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Attachment preview");

  function closeModal() {
    overlay.remove();
    document.removeEventListener("keydown", onKeyDown);
    if (triggerElement && typeof triggerElement.focus === "function") {
      triggerElement.focus();
    }
  }

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeModal();
  });

  const modal = document.createElement("div");
  modal.className = "attachment-preview-modal";

  // ── Header ──────────────────────────────────────────────────────────────
  const header = document.createElement("div");
  header.className = "attachment-preview-header";

  const title = document.createElement("span");
  title.className = "attachment-preview-title";

  const actions = document.createElement("div");
  actions.className = "attachment-preview-actions";

  const downloadBtn = document.createElement("a");
  downloadBtn.className = "attachment-preview-download";
  downloadBtn.textContent = "⬇ Download";

  const printBtn = document.createElement("button");
  printBtn.className = "attachment-preview-print";
  printBtn.textContent = "🖨 Print";
  printBtn.addEventListener("click", function () {
    window.print();
  });

  const closeBtn = document.createElement("button");
  closeBtn.className = "attachment-preview-close";
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", function () { closeModal(); });

  actions.appendChild(downloadBtn);
  actions.appendChild(printBtn);
  actions.appendChild(closeBtn);
  header.appendChild(title);
  header.appendChild(actions);
  modal.appendChild(header);

  // ── Navigation bar ───────────────────────────────────────────────────────
  const navBar = document.createElement("div");
  navBar.className = "attachment-nav-bar";
  navBar.style.display = list.length > 1 ? "" : "none";

  const prevBtn = document.createElement("button");
  prevBtn.className = "attachment-nav-btn";
  prevBtn.textContent = "‹";
  prevBtn.title = "Previous attachment";

  const nextBtn = document.createElement("button");
  nextBtn.className = "attachment-nav-btn";
  nextBtn.textContent = "›";
  nextBtn.title = "Next attachment";

  const thumbStrip = document.createElement("div");
  thumbStrip.className = "attachment-nav-strip";

  list.forEach(function (a, i) {
    const chip = document.createElement("button");
    chip.className = "attachment-nav-chip";
    chip.dataset.index = i;
    chip.title = a.filename || "attachment";

    const chipIcon = document.createElement("span");
    chipIcon.textContent = attachmentIcon(a.mime_type);
    chipIcon.className = "attachment-nav-chip-icon";

    const chipName = document.createElement("span");
    chipName.className = "attachment-nav-chip-name";
    chipName.textContent = a.filename || "attachment";

    chip.appendChild(chipIcon);
    chip.appendChild(chipName);
    chip.addEventListener("click", function () { navigateTo(i); });
    thumbStrip.appendChild(chip);
  });

  navBar.appendChild(prevBtn);
  navBar.appendChild(thumbStrip);
  navBar.appendChild(nextBtn);
  modal.appendChild(navBar);

  // ── Preview body ─────────────────────────────────────────────────────────
  const body = document.createElement("div");
  body.className = "attachment-preview-body";
  modal.appendChild(body);

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // ── Render a specific index ───────────────────────────────────────────────
  function navigateTo(newIdx) {
    idx = newIdx;
    const current = list[idx];
    const url = attDataUrl(current);

    // Update header
    title.textContent = current.filename || "Preview";
    downloadBtn.href = url;
    downloadBtn.download = current.filename || "attachment";

    // Update nav button states
    prevBtn.disabled = idx === 0;
    nextBtn.disabled = idx === list.length - 1;

    // Highlight active chip
    thumbStrip.querySelectorAll(".attachment-nav-chip").forEach(function (chip) {
      chip.classList.toggle("attachment-nav-chip--active", parseInt(chip.dataset.index) === idx);
    });

    // Scroll active chip into view
    const activeChip = thumbStrip.querySelector(".attachment-nav-chip--active");
    if (activeChip) activeChip.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });

    // Render preview content
    body.innerHTML = "";
    if (current.mime_type.startsWith("image/")) {
      const img = document.createElement("img");
      img.src = url;
      img.alt = current.filename || "image";
      img.className = "attachment-preview-image";
      body.appendChild(img);
    } else if (current.mime_type === "application/pdf") {
      const obj = document.createElement("object");
      obj.data = url + "?preview=1";
      obj.type = "application/pdf";
      obj.className = "attachment-preview-frame";
      const fallback = document.createElement("div");
      fallback.style.cssText = "padding:24px;text-align:center;color:#555;font-size:14px";
      fallback.innerHTML = 'Your browser cannot preview PDFs inline. <a href="' + url + '" download="' + (current.filename || "attachment") + '" style="color:#1a73e8">Download instead</a>.';
      obj.appendChild(fallback);
      body.appendChild(obj);
    } else {
      const frame = document.createElement("iframe");
      frame.src = url + "?preview=1";
      frame.className = "attachment-preview-frame";
      frame.setAttribute("title", current.filename || "preview");
      body.appendChild(frame);
    }
  }

  prevBtn.addEventListener("click", function () { if (idx > 0) navigateTo(idx - 1); });
  nextBtn.addEventListener("click", function () { if (idx < list.length - 1) navigateTo(idx + 1); });

  // Initial render
  navigateTo(idx);

  // Focus the close button when the modal opens
  setTimeout(function () { closeBtn.focus(); }, 0);

  // Focus trap helper — returns all currently focusable elements within the overlay
  function getFocusable() {
    return Array.from(overlay.querySelectorAll(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
    ));
  }

  // Keyboard navigation
  function onKeyDown(e) {
    if (e.key === "Escape") {
      closeModal();
    } else if (e.key === "ArrowLeft" && idx > 0) {
      navigateTo(idx - 1);
    } else if (e.key === "ArrowRight" && idx < list.length - 1) {
      navigateTo(idx + 1);
    } else if (e.key === "Tab") {
      const focusable = getFocusable();
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        // Shift+Tab: if focus is on first element, wrap to last
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        // Tab: if focus is on last element, wrap to first
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  }
  document.addEventListener("keydown", onKeyDown);
  overlay.addEventListener("remove", function () {
    document.removeEventListener("keydown", onKeyDown);
  });
}

/**
 * Opens a modal overlay to display the raw RFC 2822 source of a message.
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

const messageDetail = { render, renderBody, buildToggleButton, openSourceModal };
