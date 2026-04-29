// Message list component for the Gmail Web Viewer SPA
// Renders the paginated message table into #message-list.

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
      tr.appendChild(subjectCell);

      const dateCell = document.createElement("td");
      dateCell.textContent = message.timestamp
        ? new Date(message.timestamp).toLocaleString()
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

const messageList = { render };
