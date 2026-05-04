// Reading Pane module for the Arkchive SPA
// Manages reading pane rendering, mode switching, and responsive fallback.
// Persists the user's mode preference to localStorage.
//
// Depends on the global `state` object defined in app.js.

/**
 * resolveResponsiveFallback(mode, width)
 *
 * Pure function. Returns the effective reading pane mode given the user's
 * preferred mode and the current viewport width.
 *
 * Rules:
 *   "right"  + width < 900  → "below"
 *   "below"  + width < 600  → "none"
 *   otherwise               → mode
 *
 * @param {"right"|"below"|"none"} mode  - The user's preferred mode.
 * @param {number} width                 - The current viewport/container width in px.
 * @returns {"right"|"below"|"none"}     - The effective mode to apply.
 */
function resolveResponsiveFallback(mode, width) {
  if (mode === "right" && width < 900) {
    return "below";
  }
  if (mode === "below" && width < 600) {
    return "none";
  }
  return mode;
}

const readingPane = {
  STORAGE_KEY: "arkchive-reading-pane",

  /** @type {ResizeObserver|null} */
  _resizeObserver: null,

  /**
   * Fetches the full message by ID then renders it into #reading-pane.
   * Shows a loading state while fetching.
   *
   * @param {string} messageId
   */
  async loadAndRender(messageId) {
    const pane = document.getElementById("reading-pane");
    if (!pane) return;

    // Show loading state immediately
    pane.innerHTML = "";
    const loading = document.createElement("div");
    loading.className = "reading-pane-loading";
    loading.textContent = "Loading…";
    pane.appendChild(loading);

    try {
      const data = await api.fetchMessage(messageId);
      this.render(data);
    } catch (err) {
      this.render(null);
    }
  },

  /**
   * Renders a fully-fetched message into #reading-pane.
   *
   * Layout philosophy:
   * - The pane is a fixed-size container (right: 380px wide, below: 320px tall)
   * - Header (subject + close) is sticky at the top
   * - Meta (sender, date, labels, attachments) is compact and scrollable
   * - The message body iframe fills ALL remaining height — it does NOT
   *   auto-resize to content height. The iframe scrolls internally.
   * - This makes the panel feel like a proper split-view, not a scrolling page.
   *
   * @param {object|null|undefined} message  Full message object (with body_html, recipients, raw)
   */
  render(message) {
    const pane = document.getElementById("reading-pane");
    if (!pane) return;

    pane.innerHTML = "";

    if (!message) {
      const errorEl = document.createElement("div");
      errorEl.className = "rp-error";
      errorEl.setAttribute("role", "alert");
      errorEl.textContent = "Failed to load message";
      pane.appendChild(errorEl);
      return;
    }

    // ── Sticky header: subject + controls ────────────────────────────────
    const header = document.createElement("div");
    header.className = "rp-header";

    const subjectEl = document.createElement("div");
    subjectEl.className = "rp-subject";
    subjectEl.textContent = message.subject || "(no subject)";
    subjectEl.title = message.subject || "(no subject)";

    const controls = document.createElement("div");
    controls.className = "rp-controls";

    // HTML/text toggle
    const toggleLabel = document.createElement("label");
    toggleLabel.className = "rp-toggle";
    toggleLabel.title = "Toggle HTML / plain text";
    const toggleCheck = document.createElement("input");
    toggleCheck.type = "checkbox";
    toggleCheck.checked = true; // start in HTML mode
    const toggleTrack = document.createElement("span");
    toggleTrack.className = "rp-toggle-track";
    const toggleText = document.createElement("span");
    toggleText.className = "rp-toggle-label";
    toggleText.textContent = "HTML";
    toggleLabel.appendChild(toggleCheck);
    toggleLabel.appendChild(toggleTrack);
    toggleLabel.appendChild(toggleText);
    controls.appendChild(toggleLabel);

    // Open in full detail button
    const openBtn = document.createElement("button");
    openBtn.className = "rp-open-btn";
    openBtn.setAttribute("aria-label", "Open full message");
    openBtn.title = "Open full message";
    openBtn.textContent = "⤢";
    openBtn.addEventListener("click", function () {
      if (typeof state !== "undefined" && typeof state.onMessageSelect === "function") {
        state.onMessageSelect(message.message_id);
      }
    });
    controls.appendChild(openBtn);

    // Close button
    const closeBtn = document.createElement("button");
    closeBtn.className = "rp-close-btn";
    closeBtn.setAttribute("aria-label", "Close reading pane");
    closeBtn.title = "Close";
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", function () {
      pane.innerHTML = "";
      if (typeof state !== "undefined" && state.selectedRowIndex >= 0) {
        const rows = document.querySelectorAll("#message-list tbody tr[role='row']");
        if (rows[state.selectedRowIndex]) rows[state.selectedRowIndex].focus();
      }
    });
    controls.appendChild(closeBtn);

    header.appendChild(subjectEl);
    header.appendChild(controls);
    pane.appendChild(header);

    // ── Compact meta bar: sender · date · labels · attachments ────────────
    const meta = document.createElement("div");
    meta.className = "rp-meta";

    const sender = message.sender || {};
    const senderSpan = document.createElement("span");
    senderSpan.className = "rp-sender";
    senderSpan.textContent = sender.name || sender.email || "";
    senderSpan.title = sender.name ? sender.name + " <" + sender.email + ">" : (sender.email || "");
    meta.appendChild(senderSpan);

    const sep1 = document.createElement("span");
    sep1.className = "rp-meta-sep";
    sep1.textContent = "·";
    meta.appendChild(sep1);

    const dateSpan = document.createElement("span");
    dateSpan.className = "rp-date";
    const dateVal = message.received_date || message.timestamp;
    dateSpan.textContent = dateVal ? new Date(dateVal).toLocaleString() : "";
    meta.appendChild(dateSpan);

    // Labels (inline chips)
    const labels = message.labels || [];
    if (labels.length > 0) {
      const sep2 = document.createElement("span");
      sep2.className = "rp-meta-sep";
      sep2.textContent = "·";
      meta.appendChild(sep2);

      const labelsWrap = document.createElement("span");
      labelsWrap.className = "rp-labels";
      labels.slice(0, 3).forEach(function (label) {
        const chip = document.createElement("span");
        chip.className = "rp-label-chip";
        chip.textContent = label;
        labelsWrap.appendChild(chip);
      });
      if (labels.length > 3) {
        const more = document.createElement("span");
        more.className = "rp-label-chip rp-label-more";
        more.textContent = "+" + (labels.length - 3);
        labelsWrap.appendChild(more);
      }
      meta.appendChild(labelsWrap);
    }

    // Attachment count
    const attachments = message.attachments || [];
    if (attachments.length > 0) {
      const sep3 = document.createElement("span");
      sep3.className = "rp-meta-sep";
      sep3.textContent = "·";
      meta.appendChild(sep3);

      const attSpan = document.createElement("span");
      attSpan.className = "rp-att-count";
      attSpan.textContent = "📎 " + attachments.length;
      attSpan.title = attachments.map(function (a) { return a.filename; }).join(", ");
      meta.appendChild(attSpan);
    }

    pane.appendChild(meta);

    // ── Attachment list (collapsed by default if > 0) ─────────────────────
    if (attachments.length > 0) {
      const attachBar = document.createElement("div");
      attachBar.className = "rp-attach-bar";

      const taggedAttachments = attachments.map(function (a) {
        return Object.assign({}, a, { _messageId: message.message_id });
      });

      taggedAttachments.forEach(function (att, i) {
        const dataUrl = att.attachment_id
          ? "/api/messages/" + message.message_id + "/attachments/" + att.attachment_id + "/data"
          : "/api/messages/" + message.message_id + "/attachments/by-filename/" + encodeURIComponent(att.filename) + "/data";
        const previewable = isPreviewable(att.mime_type);

        const chip = document.createElement("button");
        chip.className = "rp-attach-chip";
        chip.title = att.filename + (att.size ? " · " + Math.ceil(att.size / 1024) + " KB" : "");
        chip.textContent = attachmentIcon(att.mime_type) + " " + att.filename;

        chip.addEventListener("click", function () {
          if (previewable && typeof openAttachmentPreview === "function") {
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

        attachBar.appendChild(chip);
      });

      pane.appendChild(attachBar);
    }

    // ── Body iframe — fills ALL remaining height ──────────────────────────
    const bodyFrame = document.createElement("iframe");
    bodyFrame.className = "rp-body-frame";
    bodyFrame.setAttribute("title", "Message body");
    // No sandbox — allow same-origin so inline images (cid:) resolve
    pane.appendChild(bodyFrame);

    // Render body content — reuse renderBody() from messageDetail.js
    function writeBody(view) {
      if (typeof renderBody === "function") {
        // renderBody auto-resizes the iframe — we override that for the pane
        // by setting height to 100% via CSS instead
        renderBody(bodyFrame, message, view);
        // Cancel the auto-resize: the pane controls height via CSS flex
        bodyFrame.style.height = "";
      } else {
        // Fallback if renderBody isn't available
        const hasHtml = message.body_html != null && message.body_html !== "";
        const doc = bodyFrame.contentDocument || bodyFrame.contentWindow.document;
        doc.open();
        if (hasHtml && view !== "text") {
          doc.write("<!DOCTYPE html><html><head><meta charset='UTF-8'>" +
            "<style>body{margin:0;padding:8px;font-family:-apple-system,sans-serif;font-size:14px}img{max-width:100%}</style>" +
            "</head><body>" + message.body_html + "</body></html>");
        } else {
          const raw = (message.body || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
          doc.write("<!DOCTYPE html><html><head><meta charset='UTF-8'>" +
            "<style>body{margin:0;padding:8px;font-family:monospace;font-size:13px;white-space:pre-wrap}</style>" +
            "</head><body>" + raw + "</body></html>");
        }
        doc.close();
      }
    }

    writeBody("html");

    // Wire toggle
    toggleCheck.addEventListener("change", function () {
      const view = toggleCheck.checked ? "html" : "text";
      toggleText.textContent = toggleCheck.checked ? "HTML" : "Text";
      writeBody(view);
      // Reset height override after renderBody sets it
      bodyFrame.style.height = "";
    });
  },

  /**
   * Clears the reading pane content.
   */
  clear() {
    const pane = document.getElementById("reading-pane");
    if (pane) {
      pane.innerHTML = "";
    }
  },

  /**
   * Applies the given reading pane mode.
   *
   * - Calls resolveResponsiveFallback(mode, viewportWidth) to get the
   *   effective mode and sets data-reading-pane on #content-area.
   * - Stores the user's *intent* (not the effective mode) to
   *   localStorage["arkchive-reading-pane"].
   * - Updates state.readingPaneMode = mode (the intent).
   *
   * @param {"right"|"below"|"none"} mode
   */
  applyMode(mode) {
    const contentArea = document.getElementById("content-area");
    const viewportWidth = contentArea ? contentArea.offsetWidth : window.innerWidth;
    const effectiveMode = resolveResponsiveFallback(mode, viewportWidth);

    if (contentArea) {
      contentArea.setAttribute("data-reading-pane", effectiveMode);
    }

    // Persist the user's intent (not the effective mode)
    try {
      localStorage.setItem(this.STORAGE_KEY, mode);
    } catch (_) {
      // localStorage unavailable — preference not persisted, but UI is updated
    }

    // Update state with the user's intent
    if (typeof state !== "undefined") {
      state.readingPaneMode = mode;
    }

    // Update the active state of the reading pane selector buttons
    this._updateSelectorButtons(mode);
  },

  /**
   * Initialises the reading pane:
   * - Restores persisted mode from localStorage["arkchive-reading-pane"].
   * - Defaults to "right" if no preference is stored.
   * - Attaches a ResizeObserver on #content-area to re-apply fallback logic
   *   on resize.
   */
  init() {
    let storedMode = null;
    try {
      storedMode = localStorage.getItem(this.STORAGE_KEY);
    } catch (_) {
      // localStorage unavailable — fall through to default
    }

    const validModes = ["right", "below", "none"];
    const mode = validModes.includes(storedMode) ? storedMode : "right";

    this.applyMode(mode);

    // Attach ResizeObserver to re-apply fallback logic on resize
    const contentArea = document.getElementById("content-area");
    if (contentArea && typeof ResizeObserver !== "undefined") {
      // Disconnect any existing observer
      if (this._resizeObserver) {
        this._resizeObserver.disconnect();
      }

      this._resizeObserver = new ResizeObserver(() => {
        // Re-apply using the stored user intent (state.readingPaneMode)
        const currentIntent =
          (typeof state !== "undefined" && state.readingPaneMode) || "right";
        const width = contentArea.offsetWidth;
        const effectiveMode = resolveResponsiveFallback(currentIntent, width);
        contentArea.setAttribute("data-reading-pane", effectiveMode);
      });

      this._resizeObserver.observe(contentArea);
    }

    // Wire up the reading pane selector buttons in the header
    this._wireHeaderButtons();
  },

  /**
   * Updates the aria-pressed / active state of the reading pane selector
   * buttons in the header to reflect the current user intent.
   *
   * @param {"right"|"below"|"none"} mode
   */
  _updateSelectorButtons(mode) {
    const buttons = document.querySelectorAll(".reading-pane-btn[data-mode]");
    buttons.forEach(function (btn) {
      const isActive = btn.getAttribute("data-mode") === mode;
      btn.setAttribute("aria-pressed", String(isActive));
      if (isActive) {
        btn.classList.add("reading-pane-btn--active");
      } else {
        btn.classList.remove("reading-pane-btn--active");
      }
    });
  },

  /**
   * Wires click handlers onto the reading pane selector buttons in the header.
   * Safe to call multiple times — replaces existing listeners via cloneNode.
   */
  _wireHeaderButtons() {
    const buttons = document.querySelectorAll(".reading-pane-btn[data-mode]");
    buttons.forEach((btn) => {
      // Replace node to remove any existing listeners
      const fresh = btn.cloneNode(true);
      btn.parentNode.replaceChild(fresh, btn);
      fresh.addEventListener("click", () => {
        const mode = fresh.getAttribute("data-mode");
        if (mode) this.applyMode(mode);
      });
    });
  },

  // Expose the pure function as a method for convenience / testability
  resolveResponsiveFallback,
};


