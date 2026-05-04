// Filters component for the Arkchive SPA
// Renders the search input and label dropdown into #filter-bar.

function render() {
  const bar = document.getElementById("filter-bar");
  bar.innerHTML = "";

  // ── Search input wrapper (input + clear button) ──────────────────────────
  const searchWrap = document.createElement("div");
  searchWrap.className = "search-wrap";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Search messages…";
  input.value = state.query;
  input.setAttribute("aria-label", "Search messages");

  const clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.className = "search-clear-btn";
  clearBtn.setAttribute("aria-label", "Clear search");
  clearBtn.title = "Clear search";
  clearBtn.textContent = "✕";
  clearBtn.hidden = !state.query;

  // Show/hide clear button as user types
  input.addEventListener("input", function () {
    clearBtn.hidden = !input.value;
  });

  // Trigger search on Enter
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      state.query = input.value;
      state.page = 1;
      state.onFilterChange();
    }
    // Clear on Escape
    if (e.key === "Escape" && input.value) {
      input.value = "";
      clearBtn.hidden = true;
      state.query = "";
      state.page = 1;
      state.onFilterChange();
    }
  });

  // Clear button click
  clearBtn.addEventListener("click", function () {
    input.value = "";
    clearBtn.hidden = true;
    state.query = "";
    state.page = 1;
    state.onFilterChange();
    input.focus();
  });

  searchWrap.appendChild(input);
  searchWrap.appendChild(clearBtn);
  bar.appendChild(searchWrap);

  // ── Label dropdown ────────────────────────────────────────────────────────
  const select = document.createElement("select");
  select.setAttribute("aria-label", "Filter by label");

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "All labels";
  select.appendChild(defaultOption);

  (state.labels || []).forEach(function (label) {
    const option = document.createElement("option");
    option.value = label;
    option.textContent = label;
    if (label === state.label) {
      option.selected = true;
    }
    select.appendChild(option);
  });

  select.addEventListener("change", function () {
    state.label = select.value;
    state.page = 1;
    state.onFilterChange();
  });
  bar.appendChild(select);
}

const filters = { render };
