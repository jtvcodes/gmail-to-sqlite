// App bootstrap and state management for the Arkchive SPA
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

  // UI preference state (new fields)
  theme: "light",
  sidebarCollapsed: false,
  readingPaneMode: "right",
  density: "cozy",
  activeLabel: "",
  selectedRowIndex: -1,
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

// Track whether a sync subprocess is actively running.
// Prevents loadMessages() from re-enabling the sync buttons mid-sync.
let _syncActive = false;
let _syncStopped = false;

function setSyncActive(active) {
  _syncActive = active;
  const primaryBtn = document.getElementById("sync-primary-btn");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (active) {
    if (primaryBtn) { primaryBtn.disabled = true; primaryBtn.classList.add("spinning"); }
    if (toggleBtn) toggleBtn.disabled = true;
  } else {
    if (primaryBtn) { primaryBtn.disabled = false; primaryBtn.classList.remove("spinning"); primaryBtn.textContent = "⇄"; }
    if (toggleBtn) toggleBtn.disabled = false;
  }
}

function setLoading(on, label) {
  const bar = document.getElementById("filter-bar");
  if (on) {
    bar.classList.add("loading");
    if (!_syncActive) {
      const primaryBtn = document.getElementById("sync-primary-btn");
      const toggleBtn = document.getElementById("sync-toggle-btn");
      if (primaryBtn) primaryBtn.disabled = true;
      if (toggleBtn) toggleBtn.disabled = true;
    }
  } else {
    bar.classList.remove("loading");
    if (!_syncActive) {
      const primaryBtn = document.getElementById("sync-primary-btn");
      const toggleBtn = document.getElementById("sync-toggle-btn");
      if (primaryBtn) { primaryBtn.disabled = false; primaryBtn.textContent = "⇄"; }
      if (toggleBtn) toggleBtn.disabled = false;
    }
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

async function refreshMessages() {
  const btn = document.getElementById("refresh-btn");
  const list = document.getElementById("message-list");
  const filterBar = document.getElementById("filter-bar");

  // Disable table + filter bar, spin the icon — no overlay
  if (btn) { btn.disabled = true; btn.classList.add("spinning"); }
  if (list) list.classList.add("refreshing");
  if (filterBar) filterBar.classList.add("loading");

  try {
    await loadLabels();
    await loadMessages({ suppressEmptyPrompt: true, silent: true });
    await loadStats();
  } finally {
    if (btn) { btn.disabled = false; btn.classList.remove("spinning"); }
    if (list) list.classList.remove("refreshing");
    if (filterBar) filterBar.classList.remove("loading");
  }
}

async function loadStats() {
  try {
    const data = await api.fetchStats();
    const el = document.getElementById("db-stats");
    const footer = document.getElementById("db-stats-footer");
    if (!el || !footer) return;
    const { total_messages, total_indexed, total_unsynced } = data;
    if (total_indexed > 0 || total_messages > 0) {
      const parts = [`${total_messages.toLocaleString()} messages in DB`];
      if (total_unsynced > 0) {
        parts.push(`${total_unsynced.toLocaleString()} pending download`);
      }
      if (total_indexed > total_messages) {
        parts.push(`${total_indexed.toLocaleString()} indexed in Gmail`);
      }
      el.textContent = parts.join("  ·  ");
      footer.removeAttribute("hidden");
    } else {
      footer.setAttribute("hidden", "");
    }
  } catch (_) {
    // Non-critical — silently ignore
  }
}

async function loadMessages({ suppressEmptyPrompt = false, silent = false } = {}) {
  if (!silent) setLoading(true);
  try {
    const data = await api.fetchMessages(state);
    state.messages = data.messages;
    state.total = data.total;
    state.error = null;
    renderError();
    renderSearchSummary();
    messageList.render();
    if (typeof sidebar !== "undefined") sidebar.render();

    const hasFilter = state.query || state.label || state.isRead !== null || state.isOutgoing !== null;
    if (data.total === 0 && !hasFilter && !suppressEmptyPrompt) {
      showNoDatabasePrompt();
    }
  } catch (err) {
    if (err.status === 503) {
      if (!suppressEmptyPrompt) showNoDatabasePrompt();
    } else {
      state.error = err.message;
      renderError();
    }
  } finally {
    if (!silent) setLoading(false);
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
  if (mode === "new") return "Sync New…";
  if (mode === "delta") return "Sync All Delta…";
  if (mode === "force") return "Sync All Forced…";
  if (mode === "test") return "Sync 10k (test)…";
  return "Syncing…";
}

// ---------------------------------------------------------------------------
// Shared SSE connection helper
// ---------------------------------------------------------------------------

function _updateSyncStatus(text) {
  // Update log console header status label
  const label = document.getElementById("sync-status-label");
  if (label) {
    if (text) {
      label.textContent = text;
      label.removeAttribute("hidden");
    } else {
      label.setAttribute("hidden", "");
    }
  }
  // Update sidebar log console button label
  const btnLabel = document.querySelector("#log-console-btn .sidebar-footer-btn-label");
  if (btnLabel) {
    btnLabel.textContent = text ? text : "Log Console";
  }
}

function _connectToSyncStream(url, onProgress) {
  return new Promise((resolve) => {
    const es = new EventSource(url);
    let lastLine = parseInt(new URL(url, location.href).searchParams.get("from") || "0", 10);

    es.onmessage = function (event) {
      if (event.lastEventId) lastLine = parseInt(event.lastEventId) + 1;
      if (onProgress) onProgress(event.data);
      if (typeof logConsole !== "undefined") logConsole.append(event.data);
      // Parse STATUS: lines and update UI
      const statusMatch = event.data.match(/STATUS:\s*(.+)/);
      if (statusMatch) _updateSyncStatus(statusMatch[1].trim());
    };
    es.addEventListener("done", function (event) {
      es.close();
      resolve({ outcome: "done", exitCode: parseInt(event.data, 10), lastLine });
    });
    es.addEventListener("error", function (event) {
      es.close();
      resolve({ outcome: "error", msg: event.data || "Sync process failed", lastLine });
    });
    es.onerror = function () {
      es.close();
      resolve({ outcome: "connection_lost", lastLine });
    };
  });
}

async function stopSync() {
  const btn = document.getElementById("sync-stop-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Stopping…"; }
  _syncStopped = true;
  try { await fetch("/api/sync/stop", { method: "POST" }); } catch (_) {}
}

async function runSync(mode) {
  closeSyncDropdown();
  if (_syncActive) return;

  _syncStopped = false;
  setSyncActive(true);

  // Show stop button in log console header, open the console
  const stopBtn = document.getElementById("sync-stop-btn");
  if (stopBtn) { stopBtn.removeAttribute("hidden"); stopBtn.disabled = false; stopBtn.textContent = "■ Stop Sync"; }
  if (typeof logConsole !== "undefined") {
    logConsole.append(`--- ${labelForMode(mode)} ---`);
    logConsole.open();
  }

  if (typeof toastManager !== "undefined") toastManager.success(labelForMode(mode));

  let result = await _connectToSyncStream(
    `/api/sync/stream?mode=${encodeURIComponent(mode)}&workers=20&from=0`,
    null
  );

  // One automatic retry on failure — but not if user stopped it
  const isFailure = result.outcome === "connection_lost" ||
                    result.outcome === "error" ||
                    (result.outcome === "done" && result.exitCode !== 0);

  if (isFailure && !_syncStopped) {
    if (typeof logConsole !== "undefined") logConsole.append("⚠ Sync ended unexpectedly — retrying…");
    await new Promise(r => setTimeout(r, 2000));
    result = await _connectToSyncStream(
      `/api/sync/stream?mode=${encodeURIComponent(mode)}&workers=20&from=${result.lastLine || 0}`,
      null
    );
  }

  // Hide stop button
  if (stopBtn) { stopBtn.setAttribute("hidden", ""); stopBtn.disabled = false; stopBtn.textContent = "■ Stop Sync"; }

  setSyncActive(false);
  _updateSyncStatus("");

  const finalFailure = result.outcome === "connection_lost" ||
                       result.outcome === "error" ||
                       (result.outcome === "done" && result.exitCode !== 0);

  if (finalFailure && !_syncStopped) {
    const failMsg = result.outcome === "connection_lost"
      ? "Lost connection to server during sync."
      : result.msg || "Sync finished with errors.";
    state.error = failMsg;
    renderError();
    if (typeof toastManager !== "undefined") toastManager.error(failMsg);
    if (typeof logConsole !== "undefined") logConsole.append(`✗ ${failMsg}`);
  } else {
    state.error = null;
    renderError();
    const noDbOverlay = document.getElementById("no-db-overlay");
    if (noDbOverlay) noDbOverlay.remove();
    if (typeof toastManager !== "undefined") toastManager.success("Sync complete");
    if (typeof logConsole !== "undefined") logConsole.append("✓ Sync complete");
    await refreshMessages();
  }
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

// ---------------------------------------------------------------------------
// Panel layout dropdown (toolbar)
// ---------------------------------------------------------------------------

const _panelModeIcons = { none: "⬜", right: "⬜▐", below: "⬜▄" };
const _panelModeOrder = ["none", "right", "below"];

function updatePanelModeBtn(mode) {
  const btn = document.getElementById("panel-mode-btn");
  if (btn) btn.textContent = _panelModeIcons[mode] || "⬜";
  // Mark active item in dropdown
  document.querySelectorAll("#panel-dropdown li[data-mode]").forEach(function (li) {
    li.classList.toggle("active", li.dataset.mode === mode);
  });
}

function setPanelMode(mode) {
  closePanelDropdown();
  if (typeof readingPane !== "undefined") readingPane.applyMode(mode);
  updatePanelModeBtn(mode);
}

function cyclePanelMode() {
  const current = (typeof state !== "undefined" && state.readingPaneMode) || "none";
  const idx = _panelModeOrder.indexOf(current);
  const next = _panelModeOrder[(idx + 1) % _panelModeOrder.length];
  setPanelMode(next);
}

function closePanelDropdown() {
  const dropdown = document.getElementById("panel-dropdown");
  const toggleBtn = document.getElementById("panel-toggle-btn");
  if (dropdown) dropdown.setAttribute("hidden", "");
  if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "false");
}

function togglePanelDropdown(event) {
  const dropdown = document.getElementById("panel-dropdown");
  const toggleBtn = document.getElementById("panel-toggle-btn");
  if (!dropdown) return;

  const isOpen = !dropdown.hasAttribute("hidden");
  if (isOpen) {
    closePanelDropdown();
  } else {
    dropdown.removeAttribute("hidden");
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
    setTimeout(() => {
      document.addEventListener("click", function onOutside(e) {
        const splitBtn = document.getElementById("panel-split-btn");
        if (splitBtn && !splitBtn.contains(e.target)) {
          closePanelDropdown();
          document.removeEventListener("click", onOutside);
        }
      });
    }, 0);
  }
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
  title.textContent = "No data found";

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
    runSync("new");
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


// ---------------------------------------------------------------------------
// Sync state persistence — survives page refresh
// ---------------------------------------------------------------------------

const SYNC_STORAGE_KEY = "gmail_sync_state";

function saveSyncState(mode, minimized) {
  try {
    localStorage.setItem(SYNC_STORAGE_KEY, JSON.stringify({
      mode,
      minimized: !!minimized,
      ts: Date.now(),
    }));
  } catch (_) {}
}

function clearSyncState() {
  try { localStorage.removeItem(SYNC_STORAGE_KEY); } catch (_) {}
}

function loadSyncState() {
  try {
    const raw = localStorage.getItem(SYNC_STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    // Discard stale state older than 2 hours (sync can't still be running)
    if (Date.now() - s.ts > 2 * 60 * 60 * 1000) {
      clearSyncState();
      return null;
    }
    return s;
  } catch (_) { return null; }
}

state.onMessageSelect = function (messageId) {
  selectMessage(messageId);
};
state.onMessageClose = function () {
  messageList.render();
};
state.onFilterChange = function () {
  loadMessages();
};

// ---------------------------------------------------------------------------
// Keyboard shortcut reference modal
// ---------------------------------------------------------------------------

function openShortcutModal() {
  if (document.getElementById("shortcut-modal-overlay")) return;

  const overlay = document.createElement("div");
  overlay.id = "shortcut-modal-overlay";
  overlay.className = "shortcut-modal-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Keyboard shortcuts");

  const modal = document.createElement("div");
  modal.className = "shortcut-modal";

  const title = document.createElement("h2");
  title.className = "shortcut-modal-title";
  title.textContent = "Keyboard Shortcuts";

  const shortcuts = [
    { key: "⌘K / Ctrl+K", desc: "Open Command Palette" },
    { key: "J",            desc: "Select next message" },
    { key: "K",            desc: "Select previous message" },
    { key: "O / Enter",    desc: "Open selected message" },
    { key: "Escape",       desc: "Close detail or palette" },
    { key: "R",            desc: "Trigger delta sync" },
    { key: "?",            desc: "Show this help" },
  ];

  const table = document.createElement("table");
  table.className = "shortcut-table";
  const tbody = document.createElement("tbody");
  shortcuts.forEach(function (s) {
    const tr = document.createElement("tr");
    const tdKey = document.createElement("td");
    tdKey.className = "shortcut-key";
    const kbd = document.createElement("kbd");
    kbd.textContent = s.key;
    tdKey.appendChild(kbd);
    const tdDesc = document.createElement("td");
    tdDesc.className = "shortcut-desc";
    tdDesc.textContent = s.desc;
    tr.appendChild(tdKey);
    tr.appendChild(tdDesc);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  const closeBtn = document.createElement("button");
  closeBtn.className = "shortcut-modal-close";
  closeBtn.setAttribute("aria-label", "Close keyboard shortcuts");
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", closeShortcutModal);

  modal.appendChild(closeBtn);
  modal.appendChild(title);
  modal.appendChild(table);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeShortcutModal();
  });

  closeBtn.focus();
}

function closeShortcutModal() {
  const overlay = document.getElementById("shortcut-modal-overlay");
  if (overlay) overlay.remove();
}

document.addEventListener("DOMContentLoaded", async function () {
  // ── Initialize modules ───────────────────────────────────────────────────
  if (typeof themeManager !== "undefined") themeManager.init();
  if (typeof sidebar !== "undefined") sidebar.init();
  if (typeof readingPane !== "undefined") readingPane.init();
  if (typeof paneResizer !== "undefined") paneResizer.init();

  // ── Wire header controls ─────────────────────────────────────────────────
  const themeToggleBtn = document.getElementById("theme-toggle-btn");
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", function () {
      if (typeof themeManager !== "undefined") themeManager.toggleTheme();
    });
  }

  const densityToggleBtn = document.getElementById("density-toggle-btn");
  if (densityToggleBtn) {
    densityToggleBtn.addEventListener("click", function () {
      if (typeof themeManager !== "undefined") themeManager.toggleDensity();
    });
  }

  if (typeof readingPane !== "undefined") {
    updatePanelModeBtn(state.readingPaneMode || "right");
  }

  document.querySelectorAll(".reading-pane-btn[data-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const mode = btn.dataset.mode;
      if (typeof readingPane !== "undefined") readingPane.applyMode(mode);
      updatePanelModeBtn(mode);
    });
  });

  // ── Global keyboard shortcuts ────────────────────────────────────────────
  document.addEventListener("keydown", function (e) {
    const tag = document.activeElement ? document.activeElement.tagName : "";
    const isEditable = document.activeElement && document.activeElement.isContentEditable;
    const isTextInput = tag === "INPUT" || tag === "TEXTAREA" || isEditable;

    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      if (typeof commandPalette !== "undefined") commandPalette.open();
      return;
    }

    if (e.key === "Escape") {
      if (document.getElementById("shortcut-modal-overlay")) { closeShortcutModal(); return; }
      if (typeof commandPalette !== "undefined") { commandPalette.close(); return; }
      if (state.selectedMessage) {
        state.selectedMessage = null;
        if (typeof messageDetail !== "undefined") messageDetail.render();
        return;
      }
      return;
    }

    if (isTextInput) return;

    if (e.key === "j" || e.key === "J") {
      e.preventDefault();
      if (state.messages.length === 0) return;
      state.selectedRowIndex = Math.min(state.selectedRowIndex + 1, state.messages.length - 1);
      if (typeof messageList !== "undefined") messageList.render();
      return;
    }
    if (e.key === "k" || e.key === "K") {
      e.preventDefault();
      if (state.messages.length === 0) return;
      state.selectedRowIndex = Math.max(state.selectedRowIndex - 1, 0);
      if (typeof messageList !== "undefined") messageList.render();
      return;
    }
    if (e.key === "o" || e.key === "O" || e.key === "Enter") {
      e.preventDefault();
      if (state.selectedRowIndex >= 0 && state.selectedRowIndex < state.messages.length) {
        const msg = state.messages[state.selectedRowIndex];
        if (msg && typeof state.onMessageSelect === "function") state.onMessageSelect(msg.message_id);
      }
      return;
    }
    if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      runSync("new");
      return;
    }
    if (e.key === "?") {
      e.preventDefault();
      openShortcutModal();
      return;
    }
  });

  // ── Sync dropdown keyboard nav ───────────────────────────────────────────
  const syncDropdown = document.getElementById("sync-dropdown");
  if (syncDropdown) {
    syncDropdown.addEventListener("keydown", function (e) {
      const items = Array.from(syncDropdown.querySelectorAll('[role="menuitem"]'));
      const focused = document.activeElement;
      const currentIndex = items.indexOf(focused);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        items[currentIndex < items.length - 1 ? currentIndex + 1 : 0].focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        items[currentIndex > 0 ? currentIndex - 1 : items.length - 1].focus();
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeSyncDropdown();
        const toggleBtn = document.getElementById("sync-toggle-btn");
        if (toggleBtn) toggleBtn.focus();
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (focused && items.includes(focused)) { focused.onclick && focused.onclick(e); closeSyncDropdown(); }
      }
    });
  }

  // ── Launch screen ────────────────────────────────────────────────────────
  function launchProgress(pct, status) {
    const bar = document.getElementById("launch-progress-bar");
    const lbl = document.getElementById("launch-status");
    if (bar) bar.style.width = pct + "%";
    if (lbl) lbl.textContent = status;
  }

  function launchDone() {
    const screen = document.getElementById("launch-screen");
    if (screen) {
      screen.classList.add("launch-hidden");
      screen.addEventListener("transitionend", function () { screen.remove(); }, { once: true });
    }
  }

  launchProgress(10, "Initializing…");
  await loadLabels();
  launchProgress(50, "Loading messages…");
  await loadMessages();
  launchProgress(85, "Loading stats…");
  await loadStats();
  launchProgress(100, "Ready");
  setTimeout(launchDone, 300);

  // ── Reconnect to in-progress sync after page refresh ─────────────────────
  try {
    const statusRes = await fetch("/api/sync/status");
    const status = await statusRes.json();
    if (status.running) {
      const mode = status.mode;
      if (typeof logConsole !== "undefined") {
        logConsole.append(`--- Reconnecting to running sync (${mode})… ---`);
      }
      setSyncActive(true);
      const stopBtn = document.getElementById("sync-stop-btn");
      if (stopBtn) { stopBtn.removeAttribute("hidden"); stopBtn.disabled = false; stopBtn.textContent = "■ Stop Sync"; }

      const result = await _connectToSyncStream(
        `/api/sync/stream?mode=${encodeURIComponent(mode)}&workers=20&from=0`,
        null
      );

      if (stopBtn) { stopBtn.setAttribute("hidden", ""); stopBtn.disabled = false; stopBtn.textContent = "■ Stop Sync"; }
      setSyncActive(false);

      if (result.outcome === "done" && result.exitCode === 0) {
        if (typeof logConsole !== "undefined") logConsole.append("✓ Sync complete");
        await refreshMessages();
      }
    }
  } catch (_) {}
});
