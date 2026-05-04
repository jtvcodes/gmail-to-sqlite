// Filters component for the Gmail Web Viewer SPA
// Renders the search input and label dropdown into #filter-bar.

function render() {
  const bar = document.getElementById("filter-bar");
  bar.innerHTML = "";

  // Search input
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Search messages...";
  input.value = state.query;
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      state.query = input.value;
      state.page = 1;
      state.onFilterChange();
    }
  });
  bar.appendChild(input);

  // Label dropdown
  const select = document.createElement("select");

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
