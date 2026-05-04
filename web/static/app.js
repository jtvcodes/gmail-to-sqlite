// App bootstrap and state management for the Gmail Web Viewer SPA
// Wires together api.js, filters.js, messageList.js, and messageDetail.js.

const state = {
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
  sortDir: "desc",  // "desc" | "asc"
};

function renderError() {
  const banner = document.getElementById("error-banner");
  if (state.error) {
    banner.textContent = state.error;
    banner.removeAttribute("hidden");
  } else {
    banner.setAttribute("hidden", "");
  }
}

function setLoading(on, label) {
  const overlay = document.getElementById("loading-overlay");
  const bar = document.getElementById("filter-bar");
  const lbl = document.getElementById("loading-label");
  const primaryBtn = document.getElementById("sync-primary-btn");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (on) {
    if (lbl) lbl.textContent = label || "";
    overlay.removeAttribute("hidden");
    bar.classList.add("loading");
    if (primaryBtn) {
      primaryBtn.disabled = true;
      primaryBtn.textContent = "⟳ Syncing…";
    }
    if (toggleBtn) toggleBtn.disabled = true;
  } else {
    overlay.setAttribute("hidden", "");
    bar.classList.remove("loading");
    if (lbl) lbl.textContent = "";
    if (primaryBtn) {
      primaryBtn.disabled = false;
      primaryBtn.textContent = "⟳ Sync New Data";
    }
    if (toggleBtn) toggleBtn.disabled = false;
  }
}

function renderSearchSummary() {
  const el = document.getElementById("search-summary");
  const hasFilter = state.query || state.label;
  if (!hasFilter) {
    el.setAttribute("hidden", "");
    return;
  }
  el.removeAttribute("hidden");
  const count = state.total;
  const parts = [];
  if (state.query) parts.push(`"<strong>${state.query}</strong>"`);
  if (state.label) parts.push(`label <strong>${state.label}</strong>`);
  el.innerHTML = `Found <strong>${count}</strong> message${count !== 1 ? "s" : ""} matching ${parts.join(" and ")}.`;
}

async function loadMessages() {
  setLoading(true);
  try {
    const data = await api.fetchMessages(state);
    state.messages = data.messages;
    state.total = data.total;
    state.error = null;
    renderError();
    renderSearchSummary();
    messageList.render();

    // Show the prompt if the DB exists but has no messages and no filters are active
    const hasFilter = state.query || state.label || state.isRead !== null || state.isOutgoing !== null;
    if (data.total === 0 && !hasFilter) {
      showNoDatabasePrompt();
    }
  } catch (err) {
    if (err.status === 503) {
      showNoDatabasePrompt();
    } else {
      state.error = err.message;
      renderError();
    }
  } finally {
    setLoading(false);
  }
}

async function loadLabels() {
  try {
    const data = await api.fetchLabels();
    state.labels = data;
    filters.render();
  } catch (err) {
    if (err.status === 503) {
      showNoDatabasePrompt();
    } else {
      state.error = err.message;
      renderError();
    }
  }
}

async function selectMessage(messageId) {
  try {
    const data = await api.fetchMessage(messageId);
    state.selectedMessage = data;
    messageDetail.render();
  } catch (err) {
    state.error = err.message;
    renderError();
  }
}

function labelForMode(mode) {
  if (mode === "delta") return "Syncing new messages…";
  if (mode === "force") return "Force-syncing all messages…";
  return "Syncing missing messages…";
}

async function runSync(mode) {
  closeSyncDropdown();

  const liveOutput = document.getElementById("sync-live-output");
  const outputPanel = document.getElementById("sync-output-panel");
  const outputText = document.getElementById("sync-output-text");

  // Clear both the live view and the summary panel
  if (liveOutput) {
    liveOutput.textContent = "";
    liveOutput.style.display = "block";
  }
  if (outputText) outputText.textContent = "";
  if (outputPanel) outputPanel.setAttribute("hidden", "");

  setLoading(true, labelForMode(mode));

  await new Promise((resolve) => {
    const es = new EventSource(`/api/sync/stream?mode=${encodeURIComponent(mode)}`);

    es.onmessage = function (event) {
      if (liveOutput) {
        liveOutput.textContent += event.data + "\n";
        liveOutput.scrollTop = liveOutput.scrollHeight;
      }
      // Mirror to the summary panel too
      if (outputText) outputText.textContent += event.data + "\n";
    };

    es.addEventListener("done", function (event) {
      es.close();
      const exitCode = parseInt(event.data, 10);

      // Hide the live output before the overlay disappears
      if (liveOutput) liveOutput.style.display = "none";

      if (exitCode !== 0) {
        state.error = "Sync finished with errors (see output below)";
        renderError();
        // Keep the summary panel visible so the user can read the errors
        if (outputPanel) {
          outputPanel.removeAttribute("hidden");
          outputPanel.open = true;
        }
      } else {
        state.error = null;
        renderError();
        const noDbOverlay = document.getElementById("no-db-overlay");
        if (noDbOverlay) noDbOverlay.remove();
        // Show summary panel collapsed (user can expand if curious)
        if (outputPanel && outputText && outputText.textContent.trim()) {
          outputPanel.removeAttribute("hidden");
          outputPanel.open = false;
        }
        loadLabels().then(() => loadMessages());
      }
      setLoading(false);
      resolve();
    });

    es.addEventListener("error", function (event) {
      es.close();
      const msg = event.data || "Sync failed";
      if (liveOutput) liveOutput.style.display = "none";
      if (outputText) outputText.textContent += `\nError: ${msg}\n`;
      if (outputPanel) {
        outputPanel.removeAttribute("hidden");
        outputPanel.open = true;
      }
      state.error = msg;
      renderError();
      setLoading(false);
      resolve();
    });

    es.onerror = function () {
      es.close();
      if (liveOutput) liveOutput.style.display = "none";
      state.error = "Lost connection to server during sync";
      renderError();
      setLoading(false);
      resolve();
    };
  });
}

// Track whether a loading operation is in progress for dropdown guard
function isSyncLoading() {
  const primaryBtn = document.getElementById("sync-primary-btn");
  return primaryBtn ? primaryBtn.disabled : false;
}

function closeSyncDropdown() {
  const dropdown = document.getElementById("sync-dropdown");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (dropdown) dropdown.setAttribute("hidden", "");
  if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "false");
}

function toggleSyncDropdown(event) {
  if (isSyncLoading()) return;

  const dropdown = document.getElementById("sync-dropdown");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (!dropdown) return;

  const isOpen = !dropdown.hasAttribute("hidden");

  if (isOpen) {
    closeSyncDropdown();
  } else {
    dropdown.removeAttribute("hidden");
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");

    // One-shot outside-click listener to close the dropdown
    function onOutsideClick(e) {
      const splitBtn = document.getElementById("sync-split-btn");
      if (splitBtn && !splitBtn.contains(e.target)) {
        closeSyncDropdown();
        document.removeEventListener("click", onOutsideClick);
      }
    }
    // Use setTimeout so this event doesn't immediately fire for the current click
    setTimeout(() => document.addEventListener("click", onOutsideClick), 0);
  }
}

// ---------------------------------------------------------------------------
// No-database prompt
// ---------------------------------------------------------------------------

function showNoDatabasePrompt() {
  // Only show once — don't stack multiple modals
  if (document.getElementById("no-db-overlay")) return;

  const overlay = document.createElement("div");
  overlay.id = "no-db-overlay";
  overlay.className = "no-db-overlay";

  const modal = document.createElement("div");
  modal.className = "no-db-modal";

  const icon = document.createElement("div");
  icon.className = "no-db-icon";
  icon.textContent = "📭";

  const title = document.createElement("h2");
  title.className = "no-db-title";
  title.textContent = "No database found";

  const body = document.createElement("p");
  body.className = "no-db-body";
  body.textContent = "No messages database was found. Would you like to start a sync to download your Gmail messages?";

  const actions = document.createElement("div");
  actions.className = "no-db-actions";

  const syncBtn = document.createElement("button");
  syncBtn.className = "no-db-sync-btn";
  syncBtn.textContent = "⟳ Start Sync";
  syncBtn.addEventListener("click", function () {
    overlay.remove();
    runSync("missing");
  });

  const dismissBtn = document.createElement("button");
  dismissBtn.className = "no-db-dismiss-btn";
  dismissBtn.textContent = "Dismiss";
  dismissBtn.addEventListener("click", function () {
    overlay.remove();
  });

  actions.appendChild(syncBtn);
  actions.appendChild(dismissBtn);
  modal.appendChild(icon);
  modal.appendChild(title);
  modal.appendChild(body);
  modal.appendChild(actions);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}


state.onMessageSelect = function (messageId) {
  selectMessage(messageId);
};
state.onMessageClose = function () {
  messageList.render();
};

document.addEventListener("DOMContentLoaded", async function () {
  // Set up keyboard navigation for the sync dropdown
  const syncDropdown = document.getElementById("sync-dropdown");
  if (syncDropdown) {
    syncDropdown.addEventListener("keydown", function (e) {
      const items = Array.from(syncDropdown.querySelectorAll('[role="menuitem"]'));
      const focused = document.activeElement;
      const currentIndex = items.indexOf(focused);

      if (e.key === "ArrowDown") {
        e.preventDefault();
        const nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
        items[nextIndex].focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
        items[prevIndex].focus();
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeSyncDropdown();
        const toggleBtn = document.getElementById("sync-toggle-btn");
        if (toggleBtn) toggleBtn.focus();
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (focused && items.includes(focused)) {
          if (typeof focused.onclick === "function") {
            focused.onclick(e);
          }
          closeSyncDropdown();
        }
      }
    });
  }

  await loadLabels();
  await loadMessages();
});
