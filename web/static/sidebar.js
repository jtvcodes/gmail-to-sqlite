// Sidebar module for the Arkchive SPA
// Manages sidebar rendering, collapse/expand, label navigation, and read/unread filter.
// Persists collapsed state to localStorage.
//
// Depends on the global `state` object defined in app.js.

// ---------------------------------------------------------------------------
// SVG icon library — inline, no external deps
// ---------------------------------------------------------------------------
const _sidebarIcons = {
  allMail: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="2,4 12,13 22,4"/></svg>`,
  inbox:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22,12 16,12 14,15 10,15 8,12 2,12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>`,
  sent:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22,2 15,22 11,13 2,9"/></svg>`,
  starred: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>`,
  important:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`,
  drafts:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`,
  trash:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="3,6 5,6 21,6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`,
  spam:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  social:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
  updates: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="23,4 23,10 17,10"/><path d="M20.49 15a9 9 0 1 1-.18-4.96"/></svg>`,
  promotions:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>`,
  forums:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  tag:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>`,
  chevronLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15,18 9,12 15,6"/></svg>`,
};

// Map Gmail system label names to icons
function _iconForLabel(label) {
  const l = label.toUpperCase();
  if (l === "INBOX")                    return _sidebarIcons.inbox;
  if (l === "SENT")                     return _sidebarIcons.sent;
  if (l === "STARRED")                  return _sidebarIcons.starred;
  if (l === "IMPORTANT")                return _sidebarIcons.important;
  if (l === "DRAFT" || l === "DRAFTS")  return _sidebarIcons.drafts;
  if (l === "TRASH")                    return _sidebarIcons.trash;
  if (l === "SPAM")                     return _sidebarIcons.spam;
  if (l === "CATEGORY_SOCIAL")          return _sidebarIcons.social;
  if (l === "CATEGORY_UPDATES")         return _sidebarIcons.updates;
  if (l === "CATEGORY_PROMOTIONS")      return _sidebarIcons.promotions;
  if (l === "CATEGORY_FORUMS")          return _sidebarIcons.forums;
  return _sidebarIcons.tag;
}

// Friendly display name for system labels
function _displayName(label) {
  const map = {
    INBOX: "Inbox", SENT: "Sent", STARRED: "Starred", IMPORTANT: "Important",
    DRAFT: "Drafts", DRAFTS: "Drafts", TRASH: "Trash", SPAM: "Spam",
    UNREAD: "Unread", CHAT: "Chat", CATEGORY_SOCIAL: "Social", CATEGORY_UPDATES: "Updates",
    CATEGORY_PROMOTIONS: "Promotions", CATEGORY_FORUMS: "Forums",
    CATEGORY_PURCHASES: "Purchases",
  };
  return map[label.toUpperCase()] || label;
}

const sidebar = {
  STORAGE_KEY: "arkchive-sidebar-collapsed",

  _isOffCanvas() {
    return window.innerWidth < 768;
  },

  render() {
    const nav = document.getElementById("sidebar");
    if (!nav) return;

    let ul = nav.querySelector("ul[role='list']");
    if (!ul) {
      ul = document.createElement("ul");
      ul.setAttribute("role", "list");
      nav.insertBefore(ul, nav.querySelector(".sidebar-footer"));
    }
    ul.innerHTML = "";

    const activeLabel = typeof state !== "undefined" ? (state.activeLabel || "") : "";

    // Helper to build a sidebar item
    const makeItem = (labelValue, iconSvg, displayText) => {
      const li = document.createElement("li");
      li.className = "sidebar-item";
      li.setAttribute("role", "listitem");
      li.setAttribute("data-label", labelValue);
      li.setAttribute("title", displayText);
      li.setAttribute("tabindex", "0");
      li.setAttribute("aria-label", displayText);
      if (activeLabel === labelValue) li.classList.add("sidebar-item--active");

      const iconEl = document.createElement("span");
      iconEl.className = "sidebar-item-icon";
      iconEl.setAttribute("aria-hidden", "true");
      iconEl.innerHTML = iconSvg;

      const textEl = document.createElement("span");
      textEl.className = "sidebar-item-label";
      textEl.textContent = displayText;

      li.appendChild(iconEl);
      li.appendChild(textEl);

      li.addEventListener("click", () => this._selectLabel(labelValue));
      li.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this._selectLabel(labelValue); }
      });
      return li;
    };

    // "All Mail" always first
    const allMailItem = makeItem("", _sidebarIcons.allMail, "All Mail");
    allMailItem.classList.add("sidebar-item-allmail");
    ul.appendChild(allMailItem);

    const labels = typeof state !== "undefined" ? (state.labels || []) : [];

    // Support both old string[] and new {label, label_type}[] formats
    const systemOrder = ["INBOX","STARRED","SNOOZED","IMPORTANT","SENT","SCHEDULED","DRAFTS","ALL_MAIL","SPAM","TRASH","CHAT"];
    const categoryOrder = ["CATEGORY_PURCHASES","CATEGORY_SOCIAL","CATEGORY_UPDATES","CATEGORY_FORUMS","CATEGORY_PROMOTIONS"];

    const systemLabels = [];
    const categoryLabels = [];
    const customLabels = [];

    labels.forEach(entry => {
      const label = typeof entry === "string" ? entry : entry.label;
      const type  = typeof entry === "string"
        ? (systemOrder.includes(label.toUpperCase()) ? "system"
          : categoryOrder.includes(label.toUpperCase()) ? "category" : "label")
        : entry.label_type;

      if (type === "system") systemLabels.push(label);
      else if (type === "category") categoryLabels.push(label);
      else customLabels.push(label);
    });

    // Sort system labels in preferred order
    systemLabels.sort((a, b) =>
      systemOrder.indexOf(a.toUpperCase()) - systemOrder.indexOf(b.toUpperCase())
    );

    // ── System labels ────────────────────────────────────────────────────
    systemLabels.forEach(label => {
      ul.appendChild(makeItem(label, _iconForLabel(label), _displayName(label)));
    });

    // ── Categories section header ────────────────────────────────────────
    if (categoryLabels.length > 0) {
      const catHeader = document.createElement("li");
      catHeader.className = "sidebar-section-header";
      catHeader.textContent = "Categories";
      ul.appendChild(catHeader);

      categoryLabels.sort((a, b) =>
        categoryOrder.indexOf(a.toUpperCase()) - categoryOrder.indexOf(b.toUpperCase())
      );
      categoryLabels.forEach(label => {
        ul.appendChild(makeItem(label, _iconForLabel(label), _displayName(label)));
      });
    }

    // ── Labels section header + tree ─────────────────────────────────────
    if (customLabels.length > 0) {
      const lblHeader = document.createElement("li");
      lblHeader.className = "sidebar-section-header";
      lblHeader.textContent = "Labels";
      ul.appendChild(lblHeader);

      // Build tree from slash-separated labels
      const tree = {};
      customLabels.sort().forEach(label => {
        const parts = label.split("/");
        let node = tree;
        parts.forEach((part, i) => {
          if (!node[part]) node[part] = { _fullPath: parts.slice(0, i + 1).join("/"), _children: {} };
          node = node[part]._children;
        });
      });

      const COLLAPSED_KEY = "arkchive-sidebar-collapsed-cats";
      let collapsedCats;
      try { collapsedCats = new Set(JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "[]")); }
      catch (_) { collapsedCats = new Set(); }

      function saveCollapsed() {
        try { localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...collapsedCats])); } catch (_) {}
      }

      function renderTree(node, parentUl, depth) {
        Object.keys(node).sort().forEach(key => {
          const entry = node[key];
          const fullPath = entry._fullPath;
          const hasChildren = Object.keys(entry._children).length > 0;

          if (hasChildren) {
            // Default collapsed on first visit
            if (!collapsedCats.has(fullPath + "__seen")) {
              collapsedCats.add(fullPath);
              collapsedCats.add(fullPath + "__seen");
              saveCollapsed();
            }

            const catLi = document.createElement("li");
            catLi.className = "sidebar-item sidebar-item--cat";
            catLi.setAttribute("data-label", fullPath);
            catLi.setAttribute("title", fullPath);
            catLi.style.paddingLeft = depth > 0 ? `${depth * 16}px` : "";
            if (activeLabel === fullPath) catLi.classList.add("sidebar-item--active");

            const iconEl = document.createElement("span");
            iconEl.className = "sidebar-item-icon";
            iconEl.setAttribute("aria-hidden", "true");
            iconEl.innerHTML = _sidebarIcons.tag;

            const textEl = document.createElement("span");
            textEl.className = "sidebar-item-label";
            textEl.textContent = key;

            const chevron = document.createElement("span");
            chevron.className = "sidebar-cat-chevron";
            chevron.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="12" height="12"><polyline points="6,9 12,15 18,9"/></svg>`;
            if (collapsedCats.has(fullPath)) chevron.classList.add("sidebar-cat-chevron--collapsed");

            catLi.appendChild(iconEl);
            catLi.appendChild(textEl);
            catLi.appendChild(chevron);

            const childUl = document.createElement("ul");
            childUl.className = "sidebar-cat-children";
            childUl.setAttribute("role", "list");
            if (collapsedCats.has(fullPath)) childUl.setAttribute("hidden", "");

            // Chevron click toggles children
            chevron.addEventListener("click", (e) => {
              e.stopPropagation();
              if (collapsedCats.has(fullPath)) {
                collapsedCats.delete(fullPath);
                childUl.removeAttribute("hidden");
                chevron.classList.remove("sidebar-cat-chevron--collapsed");
              } else {
                collapsedCats.add(fullPath);
                childUl.setAttribute("hidden", "");
                chevron.classList.add("sidebar-cat-chevron--collapsed");
              }
              saveCollapsed();
            });

            // Label click selects the category as a filter
            catLi.addEventListener("click", () => sidebar._selectLabel(fullPath));

            parentUl.appendChild(catLi);
            parentUl.appendChild(childUl);
            renderTree(entry._children, childUl, depth + 1);
          } else {
            const li = makeItem(fullPath, _iconForLabel(key), key);
            li.style.paddingLeft = depth > 0 ? `${depth * 16}px` : "";
            parentUl.appendChild(li);
          }
        });
      }

      renderTree(tree, ul, 0);
    }

    // Read/unread filter
    this._renderReadFilter(nav);
    this._updateToggleBtn();
  },

  _renderReadFilter(nav) {
    let filterDiv = nav.querySelector(".sidebar-read-filter");
    if (!filterDiv) {
      filterDiv = document.createElement("div");
      filterDiv.className = "sidebar-read-filter";
      const footer = nav.querySelector(".sidebar-footer");
      nav.insertBefore(filterDiv, footer);
    }
    filterDiv.innerHTML = "";

    const isRead = typeof state !== "undefined" ? state.isRead : null;
    const options = [
      { value: null,  label: "All" },
      { value: false, label: "Unread" },
      { value: true,  label: "Read" },
    ];
    options.forEach(({ value, label }) => {
      const btn = document.createElement("button");
      const active = isRead === value;
      btn.className = "sidebar-filter-btn" + (active ? " sidebar-filter-btn--active" : "");
      btn.textContent = label;
      btn.setAttribute("aria-pressed", String(active));
      btn.setAttribute("title", `Show ${label.toLowerCase()} messages`);
      btn.addEventListener("click", () => this._setReadFilter(value));
      filterDiv.appendChild(btn);
    });
  },

  _selectLabel(labelName) {
    if (typeof state !== "undefined") {
      state.activeLabel = labelName;
      state.label = labelName;
      state.page = 1;
    }
    const nav = document.getElementById("sidebar");
    if (nav) {
      nav.querySelectorAll("li[data-label]").forEach(li => {
        li.classList.toggle("sidebar-item--active", li.getAttribute("data-label") === labelName);
      });
    }
    if (typeof state !== "undefined" && typeof state.onFilterChange === "function") state.onFilterChange();
  },

  _setReadFilter(value) {
    if (typeof state !== "undefined") { state.isRead = value; state.page = 1; }
    this._renderReadFilter(document.getElementById("sidebar"));
    if (typeof loadMessages === "function") loadMessages();
    else if (typeof state !== "undefined" && typeof state.onFilterChange === "function") state.onFilterChange();
  },

  _updateFooterOffset() {
    const footer = document.getElementById("db-stats-footer");
    if (!footer) return;
    if (this._isOffCanvas()) {
      footer.style.left = "0";
      return;
    }
    const nav = document.getElementById("sidebar");
    const collapsed = nav && nav.classList.contains("sidebar--collapsed");
    footer.style.left = collapsed ? "52px" : "220px";
  },

  _updateToggleBtn() {
    const btn = document.getElementById("sidebar-toggle");
    if (!btn) return;
    const collapsed = typeof state !== "undefined" ? state.sidebarCollapsed : false;
    btn.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
    btn.setAttribute("title",      collapsed ? "Expand sidebar" : "Collapse sidebar");
    btn.setAttribute("aria-expanded", String(!collapsed));
    // Rotate the chevron via CSS class — no text content change
    btn.classList.toggle("sidebar-toggle--collapsed", collapsed);
  },

  collapse() {
    const nav = document.getElementById("sidebar");
    if (!nav) return;
    if (this._isOffCanvas()) nav.classList.remove("sidebar--open");
    else nav.classList.add("sidebar--collapsed");
    if (typeof state !== "undefined") state.sidebarCollapsed = true;
    this._updateToggleBtn();
    this._updateFooterOffset();
  },

  expand() {
    const nav = document.getElementById("sidebar");
    if (!nav) return;
    if (this._isOffCanvas()) nav.classList.add("sidebar--open");
    else nav.classList.remove("sidebar--collapsed");
    if (typeof state !== "undefined") state.sidebarCollapsed = false;
    this._updateToggleBtn();
    this._updateFooterOffset();
  },

  toggle() {
    const collapsed = typeof state !== "undefined" ? state.sidebarCollapsed : false;
    if (collapsed) this.expand(); else this.collapse();
    const newCollapsed = typeof state !== "undefined" ? state.sidebarCollapsed : !collapsed;
    try { localStorage.setItem(this.STORAGE_KEY, String(newCollapsed)); } catch (_) {}
  },

  init() {
    let storedCollapsed = null;
    try { storedCollapsed = localStorage.getItem(this.STORAGE_KEY); } catch (_) {}
    const shouldCollapse = storedCollapsed === "true";
    if (typeof state !== "undefined") state.sidebarCollapsed = shouldCollapse;

    const nav = document.getElementById("sidebar");
    if (nav && shouldCollapse && !this._isOffCanvas()) {
      nav.classList.add("sidebar--collapsed");
    }

    // Ensure footer with toggle button exists
    let footer = nav ? nav.querySelector(".sidebar-footer") : null;
    if (!footer && nav) {
      footer = document.createElement("div");
      footer.className = "sidebar-footer";
      nav.appendChild(footer);
    }

    // Wire toggle button
    const toggleBtn = document.getElementById("sidebar-toggle");
    if (toggleBtn) {
      const fresh = toggleBtn.cloneNode(true);
      toggleBtn.replaceWith(fresh);
      fresh.innerHTML = _sidebarIcons.chevronLeft;
      fresh.addEventListener("click", () => this.toggle());
    }

    this.render();
    this._updateFooterOffset();
  },
};

