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
  if (on) {
    if (lbl) lbl.textContent = label || "";
    overlay.removeAttribute("hidden");
    bar.classList.add("loading");
  } else {
    overlay.setAttribute("hidden", "");
    bar.classList.remove("loading");
    if (lbl) lbl.textContent = "";
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
  } catch (err) {
    state.error = err.message;
    renderError();
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
    state.error = err.message;
    renderError();
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

async function runSync() {
  const btn = document.getElementById("sync-btn");
  btn.disabled = true;
  btn.textContent = "⟳ Syncing...";
  setLoading(true, "Syncing with Gmail…");
  try {
    const resp = await fetch("/api/sync", { method: "POST" });
    const data = await resp.json();
    if (!resp.ok) {
      state.error = data.error || "Sync failed";
      renderError();
    } else {
      state.error = null;
      renderError();
      // Reload labels and messages to reflect new data
      await loadLabels();
      await loadMessages();
    }
  } catch (_err) {
    state.error = "Network error — could not reach the server";
    renderError();
  } finally {
    setLoading(false);
    btn.disabled = false;
    btn.textContent = "⟳ Sync";
  }
}

state.onFilterChange = loadMessages;
state.onMessageSelect = function (messageId) {
  selectMessage(messageId);
};
state.onMessageClose = function () {
  messageList.render();
};

document.addEventListener("DOMContentLoaded", async function () {
  await loadLabels();
  await loadMessages();
});
