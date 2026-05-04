// API client for the Gmail Web Viewer SPA
// Wraps fetch calls to the backend REST API with error handling.

async function fetchMessages(params) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.pageSize) query.set("page_size", params.pageSize);
  if (params.query) query.set("q", params.query);
  if (params.label) query.set("label", params.label);
  if (params.isRead !== null && params.isRead !== undefined) query.set("is_read", params.isRead);
  if (params.isOutgoing !== null && params.isOutgoing !== undefined) query.set("is_outgoing", params.isOutgoing);
  if (params.includeDeleted) query.set("include_deleted", params.includeDeleted);
  if (params.sortDir) query.set("sort_dir", params.sortDir);

  const url = "/api/messages" + (query.toString() ? "?" + query.toString() : "");
  return _apiFetch(url);
}

async function fetchMessage(messageId) {
  return _apiFetch("/api/messages/" + encodeURIComponent(messageId));
}

async function fetchLabels() {
  return _apiFetch("/api/labels");
}

async function fetchStats() {
  return _apiFetch("/api/messages/stats");
}

async function _apiFetch(url) {
  let response;
  try {
    response = await fetch(url);
  } catch (_err) {
    throw new Error("Network error — please check the server is running");
  }

  if (!response.ok) {
    let message;
    try {
      const body = await response.json();
      message = body.error || response.statusText;
    } catch (_err) {
      message = response.statusText;
    }
    const err = new Error(message);
    err.status = response.status;
    throw err;
  }

  return response.json();
}

const api = { fetchMessages, fetchMessage, fetchLabels, fetchStats };
