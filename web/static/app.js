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

// Track whether a sync subprocess is actively running.
// Prevents loadMessages() from re-enabling the sync buttons mid-sync.
let _syncActive = false;

function setSyncActive(active) {
  _syncActive = active;
  const primaryBtn = document.getElementById("sync-primary-btn");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (active) {
    if (primaryBtn) { primaryBtn.disabled = true; primaryBtn.textContent = "⟳ Syncing…"; }
    if (toggleBtn) toggleBtn.disabled = true;
  } else {
    if (primaryBtn) { primaryBtn.disabled = false; primaryBtn.textContent = "⟳ Sync New Data"; }
    if (toggleBtn) toggleBtn.disabled = false;
  }
}

function setLoading(on, label) {
  const overlay = document.getElementById("loading-overlay");
  const bar = document.getElementById("filter-bar");
  const lbl = document.getElementById("loading-label");
  const restoreTab = document.getElementById("sync-restore-tab");
  const minimizeBtn = document.getElementById("sync-minimize-btn");
  if (on) {
    if (lbl) lbl.textContent = label || "";
    // Only show overlay if not currently minimized
    if (!overlay.dataset.minimized) {
      overlay.removeAttribute("hidden");
    }
    // Minimize button hidden by default — runSync() enables it explicitly
    if (minimizeBtn) minimizeBtn.setAttribute("hidden", "");
    bar.classList.add("loading");
    // Only disable sync buttons if a sync isn't already holding them disabled
    if (!_syncActive) {
      const primaryBtn = document.getElementById("sync-primary-btn");
      const toggleBtn = document.getElementById("sync-toggle-btn");
      if (primaryBtn) primaryBtn.disabled = true;
      if (toggleBtn) toggleBtn.disabled = true;
    }
  } else {
    // Only fully reset the overlay if we're not in minimized mode.
    const isMinimized = !!overlay.dataset.minimized;
    if (!isMinimized) {
      overlay.setAttribute("hidden", "");
      if (restoreTab) restoreTab.setAttribute("hidden", "");
    }
    if (minimizeBtn) minimizeBtn.setAttribute("hidden", "");
    bar.classList.remove("loading");
    if (lbl && !isMinimized) lbl.textContent = "";
    // Only re-enable sync buttons if no sync is running
    if (!_syncActive) {
      const primaryBtn = document.getElementById("sync-primary-btn");
      const toggleBtn = document.getElementById("sync-toggle-btn");
      if (primaryBtn) { primaryBtn.disabled = false; primaryBtn.textContent = "⟳ Sync New Data"; }
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
  if (btn) { btn.disabled = true; btn.textContent = "↺ Refreshing…"; }
  try {
    await loadLabels();
    await loadMessages({ suppressEmptyPrompt: true, silent: true });
    await loadStats();
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "↺ Refresh"; }
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
  if (mode === "delta") return "Syncing new messages…";
  if (mode === "force") return "Force-syncing all messages…";
  if (mode === "test") return "Test sync (10k messages)…";
  return "Syncing missing messages…";
}

async function runSync(mode) {
  closeSyncDropdown();

  const liveWrap = document.getElementById("sync-live-output-wrap");
  const liveOutput = document.getElementById("sync-live-output");
  const scrollBtn = document.getElementById("sync-scroll-btn");
  const outputPanel = document.getElementById("sync-output-panel");
  const outputText = document.getElementById("sync-output-text");
  const overlay = document.getElementById("loading-overlay");

  // Mark sync as active — prevents loadMessages() from re-enabling sync buttons
  setSyncActive(true);

  // Clear both the live view and the summary panel
  if (liveOutput) liveOutput.textContent = "";
  if (liveWrap) liveWrap.style.display = "block";
  if (outputText) outputText.textContent = "";
  if (outputPanel) outputPanel.setAttribute("hidden", "");

  setLoading(true, labelForMode(mode));

  // Persist sync state so a page refresh can reconnect
  saveSyncState(mode, false);

  // Enable minimize now that we're in a sync (not a plain load)
  const minimizeBtn = document.getElementById("sync-minimize-btn");
  if (minimizeBtn) minimizeBtn.removeAttribute("hidden");

  // --- Scroll-lock logic ---
  let autoScroll = true;

  function isAtBottom() {
    if (!liveOutput) return true;
    return liveOutput.scrollHeight - liveOutput.scrollTop - liveOutput.clientHeight < 4;
  }

  function setScrollBtn(visible) {
    if (!scrollBtn) return;
    if (visible) scrollBtn.removeAttribute("hidden");
    else scrollBtn.setAttribute("hidden", "");
  }

  let programmaticScroll = false;

  function onScroll() {
    if (programmaticScroll) return;
    if (isAtBottom()) { autoScroll = true; setScrollBtn(false); }
    else { autoScroll = false; setScrollBtn(true); }
  }

  function resumeScroll() {
    autoScroll = true;
    setScrollBtn(false);
    if (liveOutput) {
      programmaticScroll = true;
      liveOutput.scrollTop = liveOutput.scrollHeight;
      requestAnimationFrame(() => { programmaticScroll = false; });
    }
  }

  if (liveOutput) liveOutput.addEventListener("scroll", onScroll);
  if (scrollBtn) scrollBtn.addEventListener("click", resumeScroll);

  let scrollPending = false;
  function scheduleScroll() {
    if (!autoScroll || scrollPending || !liveOutput) return;
    scrollPending = true;
    requestAnimationFrame(() => {
      programmaticScroll = true;
      liveOutput.scrollTop = liveOutput.scrollHeight;
      scrollPending = false;
      requestAnimationFrame(() => { programmaticScroll = false; });
    });
  }

  function cleanup() {
    if (liveOutput) liveOutput.removeEventListener("scroll", onScroll);
    if (scrollBtn) scrollBtn.removeEventListener("click", resumeScroll);
    setScrollBtn(false);
    if (liveWrap) liveWrap.style.display = "none";
  }

  const summaryLines = [];
  let syncTotal = 0;
  let syncDone = 0;

  function updateProgressLabel() {
    const lbl = document.getElementById("loading-label");
    if (!lbl) return;
    if (syncTotal > 0) {
      lbl.textContent = `Syncing messages ${syncDone} of ${syncTotal}…`;
    }
  }

  // --- Single SSE attempt — returns "done", "error", or "connection_lost" ---
  function attemptSync(attemptLabel, fromLine) {
    return new Promise((resolve) => {
      if (attemptLabel && liveOutput) {
        liveOutput.appendChild(document.createTextNode(`\n--- ${attemptLabel} ---\n`));
      }

      const url = `/api/sync/stream?mode=${encodeURIComponent(mode)}&workers=20&from=${fromLine || 0}`;
      const es = new EventSource(url);
      let lastLine = fromLine || 0;

      es.onmessage = function (event) {
        if (liveOutput) {
          liveOutput.appendChild(document.createTextNode(event.data + "\n"));
          scheduleScroll();
        }
        summaryLines.push(event.data);
        if (event.lastEventId) lastLine = parseInt(event.lastEventId) + 1;

        const foundMatch = event.data.match(/Found (\d+) messages? to sync\./);
        if (foundMatch) { syncTotal = parseInt(foundMatch[1], 10); syncDone = 0; updateProgressLabel(); }
        if (syncTotal > 0 && /Successfully synced message/.test(event.data)) {
          syncDone += 1; updateProgressLabel();
        }
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

  // --- Run with one automatic retry on connection loss or process crash ---
  let result = await attemptSync(null, 0);

  const isFailure = result.outcome === "connection_lost" ||
                    result.outcome === "error" ||
                    (result.outcome === "done" && result.exitCode !== 0);

  if (isFailure) {
    const retryMsg = result.outcome === "connection_lost"
      ? "Connection lost — retrying…"
      : "Sync process ended unexpectedly — retrying…";

    if (liveOutput) {
      liveOutput.appendChild(document.createTextNode(`\n⚠ ${retryMsg}\n`));
      scheduleScroll();
    }
    const lbl = document.getElementById("loading-label");
    if (lbl) lbl.textContent = retryMsg;

    await new Promise(r => setTimeout(r, 2000));

    syncTotal = 0; syncDone = 0;
    // Resume from where we left off
    result = await attemptSync("Retry attempt", result.lastLine || 0);
  }

  // --- Handle final result ---
  cleanup();

  const finalFailure = result.outcome === "connection_lost" ||
                       result.outcome === "error" ||
                       (result.outcome === "done" && result.exitCode !== 0);

  if (outputText) outputText.textContent = summaryLines.join("\n");

  if (finalFailure) {
    // Show the failure panel with a "Try Again" button
    const failMsg = result.outcome === "connection_lost"
      ? "Lost connection to server during sync."
      : result.msg || "Sync finished with errors.";

    if (outputPanel) {
      outputPanel.removeAttribute("hidden");
      outputPanel.open = true;
    }

    // Inject "Try Again" button into the output panel if not already there
    const existingRetryBtn = document.getElementById("sync-retry-btn");
    if (existingRetryBtn) existingRetryBtn.remove();

    const retryBanner = document.createElement("div");
    retryBanner.className = "sync-retry-banner";

    const retryMsg = document.createElement("span");
    retryMsg.textContent = "Sync failed — please try again later.";

    const retryBtn = document.createElement("button");
    retryBtn.id = "sync-retry-btn";
    retryBtn.className = "sync-retry-btn";
    retryBtn.textContent = "↺ Try Again";
    retryBtn.addEventListener("click", function () {
      retryBanner.remove();
      runSync(mode);
    });

    retryBanner.appendChild(retryMsg);
    retryBanner.appendChild(retryBtn);

    // Insert before the output panel summary
    const main = document.querySelector("main");
    if (main) main.insertBefore(retryBanner, outputPanel);

    state.error = failMsg;
    renderError();
  } else {
    // Success
    state.error = null;
    renderError();
    const noDbOverlay = document.getElementById("no-db-overlay");
    if (noDbOverlay) noDbOverlay.remove();
    if (outputPanel && outputText && outputText.textContent.trim()) {
      outputPanel.removeAttribute("hidden");
      outputPanel.open = false;
    }
    loadLabels().then(() => loadMessages()).then(() => loadStats());
  }

  delete overlay.dataset.minimized;
  clearSyncState();
  setSyncActive(false);
  setLoading(false);
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
// Reconnect to an already-running sync (after page refresh)
// ---------------------------------------------------------------------------

async function _reconnectToSync(mode) {
  const liveWrap = document.getElementById("sync-live-output-wrap");
  const liveOutput = document.getElementById("sync-live-output");
  const scrollBtn = document.getElementById("sync-scroll-btn");
  const outputPanel = document.getElementById("sync-output-panel");
  const outputText = document.getElementById("sync-output-text");
  const overlay = document.getElementById("loading-overlay");

  if (liveOutput) liveOutput.textContent = "";
  if (liveWrap) liveWrap.style.display = "block";
  if (outputText) outputText.textContent = "";
  if (outputPanel) outputPanel.setAttribute("hidden", "");

  setLoading(true, labelForMode(mode));
  setSyncActive(true);
  saveSyncState(mode, false);

  const minimizeBtn = document.getElementById("sync-minimize-btn");
  if (minimizeBtn) minimizeBtn.removeAttribute("hidden");

  // --- Scroll-lock logic (same as runSync) ---
  let autoScroll = true;
  let programmaticScroll = false;
  let scrollPending = false;

  function isAtBottom() {
    if (!liveOutput) return true;
    return liveOutput.scrollHeight - liveOutput.scrollTop - liveOutput.clientHeight < 4;
  }
  function setScrollBtn(visible) {
    if (!scrollBtn) return;
    if (visible) scrollBtn.removeAttribute("hidden");
    else scrollBtn.setAttribute("hidden", "");
  }
  function onScroll() {
    if (programmaticScroll) return;
    if (isAtBottom()) { autoScroll = true; setScrollBtn(false); }
    else { autoScroll = false; setScrollBtn(true); }
  }
  function resumeScroll() {
    autoScroll = true;
    setScrollBtn(false);
    if (liveOutput) {
      programmaticScroll = true;
      liveOutput.scrollTop = liveOutput.scrollHeight;
      requestAnimationFrame(() => { programmaticScroll = false; });
    }
  }
  function scheduleScroll() {
    if (!autoScroll || scrollPending || !liveOutput) return;
    scrollPending = true;
    requestAnimationFrame(() => {
      programmaticScroll = true;
      liveOutput.scrollTop = liveOutput.scrollHeight;
      scrollPending = false;
      requestAnimationFrame(() => { programmaticScroll = false; });
    });
  }

  if (liveOutput) liveOutput.addEventListener("scroll", onScroll);
  if (scrollBtn) scrollBtn.addEventListener("click", resumeScroll);

  function cleanup() {
    if (liveOutput) liveOutput.removeEventListener("scroll", onScroll);
    if (scrollBtn) scrollBtn.removeEventListener("click", resumeScroll);
    setScrollBtn(false);
    if (liveWrap) liveWrap.style.display = "none";
  }

  // Plug into the existing stream from line 0 (replay full log)
  const summaryLines = [];
  let syncTotal = 0;
  let syncDone = 0;

  function updateProgressLabel() {
    const lbl = document.getElementById("loading-label");
    if (!lbl) return;
    if (syncTotal > 0) lbl.textContent = `Syncing messages ${syncDone} of ${syncTotal}…`;
  }

  const url = `/api/sync/stream?mode=${encodeURIComponent(mode)}&workers=20&from=0`;
  const es = new EventSource(url);

  es.onmessage = function (event) {
    if (liveOutput) {
      liveOutput.appendChild(document.createTextNode(event.data + "\n"));
      scheduleScroll();
    }
    summaryLines.push(event.data);
    const foundMatch = event.data.match(/Found (\d+) messages? to sync\./);
    if (foundMatch) { syncTotal = parseInt(foundMatch[1], 10); syncDone = 0; updateProgressLabel(); }
    if (syncTotal > 0 && /Successfully synced message/.test(event.data)) {
      syncDone += 1; updateProgressLabel();
    }
  };

  es.addEventListener("done", function (event) {
    es.close();
    cleanup();
    if (outputText) outputText.textContent = summaryLines.join("\n");
    const exitCode = parseInt(event.data, 10);
    if (exitCode === 0) {
      if (outputPanel && outputText && outputText.textContent.trim()) {
        outputPanel.removeAttribute("hidden");
        outputPanel.open = false;
      }
      loadLabels().then(() => loadMessages()).then(() => loadStats());
    } else {
      if (outputPanel) { outputPanel.removeAttribute("hidden"); outputPanel.open = true; }
      state.error = "Sync finished with errors (see output below)";
      renderError();
    }
    delete overlay.dataset.minimized;
    clearSyncState();
    setSyncActive(false);
    setLoading(false);
  });

  es.addEventListener("error", function () { es.close(); cleanup(); setSyncActive(false); });
  es.onerror = function () { es.close(); cleanup(); setSyncActive(false); };
}

document.addEventListener("DOMContentLoaded", async function () {
  // Minimize / restore sync window
  const minimizeBtn = document.getElementById("sync-minimize-btn");
  const restoreTab = document.getElementById("sync-restore-tab");
  const overlay = document.getElementById("loading-overlay");
  const restoreLabel = document.getElementById("sync-restore-label");

  if (minimizeBtn) {
    minimizeBtn.addEventListener("click", function () {
      overlay.setAttribute("hidden", "");
      overlay.dataset.minimized = "1";
      if (restoreTab) restoreTab.removeAttribute("hidden");
      const savedSync = loadSyncState();
      if (savedSync) saveSyncState(savedSync.mode, true);
      refreshMessages();
    });
  }

  if (restoreTab) {
    restoreTab.addEventListener("click", function () {
      const pendingMode = restoreTab.dataset.pendingReconnect;
      delete restoreTab.dataset.pendingReconnect;

      restoreTab.setAttribute("hidden", "");
      delete overlay.dataset.minimized;

      if (pendingMode) {
        // After page refresh — plug into the running sync
        _reconnectToSync(pendingMode);
      } else {
        // Normal restore — just show the overlay again
        overlay.removeAttribute("hidden");
        if (minimizeBtn) minimizeBtn.removeAttribute("hidden");
        const savedSync = loadSyncState();
        if (savedSync) saveSyncState(savedSync.mode, false);
      }
    });
  }

  // Keep restore tab label in sync with loading-label
  const loadingLabel = document.getElementById("loading-label");
  if (loadingLabel && restoreLabel) {
    const observer = new MutationObserver(function () {
      restoreLabel.textContent = loadingLabel.textContent || "Syncing…";
    });
    observer.observe(loadingLabel, { childList: true, characterData: true, subtree: true });
  }
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
  await loadStats();

  // --- Reconnect to in-progress sync after page refresh ---
  try {
    const statusRes = await fetch("/api/sync/status");
    const status = await statusRes.json();
    if (status.running) {
      const mode = status.mode;
      const savedSync = loadSyncState();
      const minimized = savedSync && savedSync.mode === mode && savedSync.minimized;

      if (minimized) {
        // Show restore tab — clicking it will plug into the running sync
        saveSyncState(mode, true);
        const restoreTabEl = document.getElementById("sync-restore-tab");
        const restoreLabelEl = document.getElementById("sync-restore-label");
        // Use live progress label if available, fall back to mode label
        if (restoreLabelEl) {
          restoreLabelEl.textContent = status.progress_label || labelForMode(mode);
        }
        if (restoreTabEl) restoreTabEl.removeAttribute("hidden");
        restoreTabEl.dataset.pendingReconnect = mode;
      } else {
        // Show the sync window and plug in immediately
        _reconnectToSync(mode);
      }
    } else {
      clearSyncState();
    }
  } catch (_) {
    // Status check failed — not critical
  }
});
