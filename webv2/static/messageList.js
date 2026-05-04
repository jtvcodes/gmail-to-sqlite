// Message list component for the Gmail Web Viewer SPA
// Renders the paginated message table into #message-list.

/**
 * Returns the best available display date for a message.
 * Prefers received_date; falls back to timestamp.
 */
function getDisplayDate(msg) {
  return msg.received_date || msg.timestamp;
}

function render() {
  const container = document.getElementById("message-list");
  container.innerHTML = "";

  // Messages arrive pre-sorted from the API
  const sorted = state.messages || [];

  // Build table
  const table = document.createElement("table");

  // Header
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["From", "Subject", "Date", "Status"].forEach(function (col) {
    const th = document.createElement("th");
    if (col === "Date") {
      th.classList.add("sortable");
      const arrow = state.sortDir === "asc" ? " ↑ oldest first" : " ↓ newest first";
      th.textContent = col + arrow;
      th.title = "Click to sort by date";
      th.addEventListener("click", function () {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        state.onFilterChange();
      });
    } else {
      th.textContent = col;
    }
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Body
  const tbody = document.createElement("tbody");

  if (sorted.length === 0) {
    const emptyRow = document.createElement("tr");
    const emptyCell = document.createElement("td");
    emptyCell.colSpan = 4;
    emptyCell.textContent = "No messages found.";
    emptyRow.appendChild(emptyCell);
    tbody.appendChild(emptyRow);
  } else {
    sorted.forEach(function (message) {
      const tr = document.createElement("tr");

      if (message.is_read === false) tr.classList.add("unread");
      if (message.is_deleted === true) tr.classList.add("deleted");

      tr.addEventListener("click", function () {
        state.onMessageSelect(message.message_id);
      });

      const fromCell = document.createElement("td");
      const sender = message.sender || {};
      fromCell.textContent = sender.name || sender.email || "";
      tr.appendChild(fromCell);

      const subjectCell = document.createElement("td");
      subjectCell.textContent = message.subject || "(no subject)";
      if (message.has_attachments) {
        const clip = document.createElement("span");
        clip.textContent = " 📎";
        clip.title = "View attachments";
        clip.className = "attachment-clip";
        clip.addEventListener("click", function (e) {
          e.stopPropagation(); // don't open the message
          openAttachmentPopover(clip, message.message_id);
        });
        subjectCell.appendChild(clip);
      }
      tr.appendChild(subjectCell);

      const dateCell = document.createElement("td");
      const displayDate = getDisplayDate(message);
      dateCell.textContent = displayDate
        ? new Date(displayDate).toLocaleString()
        : "";
      tr.appendChild(dateCell);

      const statusCell = document.createElement("td");
      statusCell.textContent = message.is_read === false ? "Unread" : "Read";
      tr.appendChild(statusCell);

      tbody.appendChild(tr);
    });
  }

  table.appendChild(tbody);
  container.appendChild(table);

  // Pagination controls
  const totalPages = Math.ceil((state.total || 0) / (state.pageSize || 50));
  const currentPage = state.page || 1;

  const pagination = document.createElement("div");
  pagination.className = "pagination";

  const prevBtn = document.createElement("button");
  prevBtn.textContent = "Previous";
  prevBtn.disabled = currentPage <= 1;
  prevBtn.addEventListener("click", function () {
    state.page = currentPage - 1;
    state.onFilterChange();
  });
  pagination.appendChild(prevBtn);

  const pageInfo = document.createElement("span");
  pageInfo.className = "page-info";
  pageInfo.textContent = "Page " + currentPage + " of " + (totalPages || 1);
  pagination.appendChild(pageInfo);

  const nextBtn = document.createElement("button");
  nextBtn.textContent = "Next";
  nextBtn.disabled = currentPage >= totalPages;
  nextBtn.addEventListener("click", function () {
    state.page = currentPage + 1;
    state.onFilterChange();
  });
  pagination.appendChild(nextBtn);

  container.appendChild(pagination);
}

const messageList = { render, getDisplayDate };

/**
 * Fetches attachments for a message and shows a popover near the clip icon.
 */
async function openAttachmentPopover(anchor, messageId) {
  // Remove any existing popover
  const existing = document.getElementById("attachment-popover");
  if (existing) {
    existing.remove();
    // If clicking the same clip again, just close
    if (existing.dataset.messageId === messageId) return;
  }

  const popover = document.createElement("div");
  popover.id = "attachment-popover";
  popover.className = "attachment-popover";
  popover.dataset.messageId = messageId;
  popover.textContent = "Loading…";
  document.body.appendChild(popover);

  // Position near the anchor
  function reposition() {
    const rect = anchor.getBoundingClientRect();
    const scrollY = window.scrollY || document.documentElement.scrollTop;
    const scrollX = window.scrollX || document.documentElement.scrollLeft;
    popover.style.top = (rect.bottom + scrollY + 6) + "px";
    popover.style.left = (rect.left + scrollX) + "px";
  }
  reposition();

  // Close on outside click
  function onOutsideClick(e) {
    if (!popover.contains(e.target) && e.target !== anchor) {
      popover.remove();
      document.removeEventListener("click", onOutsideClick);
      document.removeEventListener("keydown", onEscape);
    }
  }
  function onEscape(e) {
    if (e.key === "Escape") {
      popover.remove();
      document.removeEventListener("click", onOutsideClick);
      document.removeEventListener("keydown", onEscape);
    }
  }
  setTimeout(function () {
    document.addEventListener("click", onOutsideClick);
    document.addEventListener("keydown", onEscape);
  }, 0);

  // Fetch message detail to get attachments
  let attachments = [];
  try {
    const data = await api.fetchMessage(messageId);
    attachments = (data.attachments || []).filter(function (a) {
      return a.filename && !a.mime_type.startsWith("multipart/");
    });
  } catch (err) {
    popover.textContent = "Failed to load attachments.";
    return;
  }

  popover.innerHTML = "";

  if (attachments.length === 0) {
    popover.textContent = "No attachments found.";
    return;
  }

  // Stamp message_id on each attachment for the preview modal URL builder
  const taggedAttachments = attachments.map(function (a) {
    return Object.assign({}, a, { _messageId: messageId });
  });

  const title = document.createElement("div");
  title.className = "attachment-popover-title";
  title.textContent = taggedAttachments.length + " attachment" + (taggedAttachments.length !== 1 ? "s" : "");
  popover.appendChild(title);

  taggedAttachments.forEach(function (att, i) {
    const dataUrl = att.attachment_id
      ? "/api/messages/" + messageId + "/attachments/" + att.attachment_id + "/data"
      : "/api/messages/" + messageId + "/attachments/by-filename/" + encodeURIComponent(att.filename) + "/data";

    const item = document.createElement("div");
    item.className = "attachment-popover-item";

    const icon = document.createElement("span");
    icon.textContent = attachmentIcon(att.mime_type);
    icon.className = "attachment-popover-icon";

    const name = document.createElement("span");
    name.className = "attachment-popover-name";
    name.textContent = att.filename;

    const kb = att.size ? Math.ceil(att.size / 1024) + " KB" : "";
    if (kb) {
      const size = document.createElement("span");
      size.className = "attachment-popover-size";
      size.textContent = kb;
      item.appendChild(icon);
      item.appendChild(name);
      item.appendChild(size);
    } else {
      item.appendChild(icon);
      item.appendChild(name);
    }

    item.addEventListener("click", function (e) {
      e.stopPropagation();
      popover.remove();
      document.removeEventListener("click", onOutsideClick);
      document.removeEventListener("keydown", onEscape);
      if (isPreviewable(att.mime_type)) {
        openAttachmentPreview(att, dataUrl, taggedAttachments, i);
      } else {
        const a = document.createElement("a");
        a.href = dataUrl;
        a.download = att.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      }
    });

    popover.appendChild(item);
  });

  reposition();
}
