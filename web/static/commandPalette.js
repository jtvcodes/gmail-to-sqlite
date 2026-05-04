// Command Palette for the Arkchive SPA
// Provides a keyboard-triggered overlay for searching and executing app actions.
//
// Depends on globals that may not exist in all contexts (runSync, themeManager,
// sidebar, toastManager) — all references are guarded with typeof checks.

const commandPalette = {
  /**
   * Built-in actions available in the command palette.
   * Each action's run() function guards against missing globals.
   */
  ACTIONS: [
    {
      id: "sync-delta",
      label: "Sync New Data",
      run: () => {
        if (typeof runSync === "function") runSync("delta");
      },
    },
    {
      id: "sync-force",
      label: "Force Sync All",
      run: () => {
        if (typeof runSync === "function") runSync("force");
      },
    },
    {
      id: "sync-missing",
      label: "Sync Missing",
      run: () => {
        if (typeof runSync === "function") runSync("missing");
      },
    },
    {
      id: "toggle-theme",
      label: "Toggle Dark Mode",
      run: () => {
        if (typeof themeManager !== "undefined" && typeof themeManager.toggleTheme === "function") {
          themeManager.toggleTheme();
        }
      },
    },
    {
      id: "toggle-sidebar",
      label: "Collapse Sidebar",
      run: () => {
        if (typeof sidebar !== "undefined" && typeof sidebar.toggle === "function") {
          sidebar.toggle();
        }
      },
    },
  ],

  /** The element that had focus before the palette was opened. */
  _triggerElement: null,

  /** Index of the currently focused result item (-1 = input focused). */
  _focusedIndex: -1,

  /** Currently rendered (filtered) actions. */
  _currentResults: [],

  /**
   * Opens the command palette overlay.
   * Renders the dialog into #command-palette-container and focuses the input.
   */
  open() {
    // Remember what had focus so we can restore it on close
    this._triggerElement = document.activeElement;

    const container = document.getElementById("command-palette-container");
    if (!container) return;

    // Avoid opening twice
    if (container.querySelector(".cp-overlay")) return;

    // Build the overlay
    const overlay = document.createElement("div");
    overlay.className = "cp-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Command Palette");

    const dialog = document.createElement("div");
    dialog.className = "cp-dialog";

    // Input
    const input = document.createElement("input");
    input.type = "text";
    input.className = "cp-input";
    input.placeholder = "Type a command…";
    input.setAttribute("aria-label", "Search commands");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");

    // Results list
    const results = document.createElement("ul");
    results.className = "cp-results";
    results.setAttribute("role", "listbox");
    results.setAttribute("aria-label", "Command results");

    dialog.appendChild(input);
    dialog.appendChild(results);
    overlay.appendChild(dialog);
    container.appendChild(overlay);

    // Reset state
    this._focusedIndex = -1;
    this._currentResults = this.ACTIONS.slice();

    // Render initial (unfiltered) results
    this._renderResults(this._currentResults, results);

    // Wire up input handler
    input.addEventListener("input", () => {
      this._focusedIndex = -1;
      const filtered = this.filter(input.value, this.ACTIONS);
      this._currentResults = filtered;
      this._renderResults(filtered, results);
    });

    // Wire up keyboard navigation
    overlay.addEventListener("keydown", (e) => this._handleKeydown(e));

    // Close on backdrop click (click on overlay but not dialog)
    overlay.addEventListener("mousedown", (e) => {
      if (e.target === overlay) this.close();
    });

    // Focus the input immediately
    input.focus();
  },

  /**
   * Closes the command palette overlay without executing any action.
   * Returns focus to the element that triggered the palette.
   */
  close() {
    const container = document.getElementById("command-palette-container");
    if (!container) return;

    const overlay = container.querySelector(".cp-overlay");
    if (overlay) {
      overlay.remove();
    }

    this._focusedIndex = -1;
    this._currentResults = [];

    // Restore focus to the triggering element
    if (this._triggerElement && typeof this._triggerElement.focus === "function") {
      try {
        this._triggerElement.focus();
      } catch (_) {
        // Focus restoration failed — not critical
      }
    }
    this._triggerElement = null;
  },

  /**
   * Filters actions by a case-insensitive substring match on label.
   * Must complete within 100ms.
   *
   * @param {string} query - The search string.
   * @param {Array} [actions] - Optional action list (defaults to this.ACTIONS for testability).
   * @returns {Array} Matching actions (subset of the provided actions list).
   */
  filter(query, actions = this.ACTIONS) {
    const q = (query || "").toLowerCase();

    return q === ""
      ? actions.slice()
      : actions.filter((action) => action.label.toLowerCase().includes(q));
  },

  /**
   * Executes the action with the given ID and closes the palette.
   * Wraps the action's run() in try/catch — on error, closes the palette
   * and shows an error toast if toastManager is available.
   *
   * @param {string} actionId
   */
  execute(actionId) {
    const action = this.ACTIONS.find((a) => a.id === actionId);
    this.close();

    if (!action) return;

    try {
      action.run();
    } catch (err) {
      const msg = (err && err.message) ? err.message : String(err);
      if (typeof toastManager !== "undefined" && typeof toastManager.error === "function") {
        toastManager.error(msg);
      }
    }
  },

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * Renders a list of action items into the results <ul>.
   * @param {Array} actions
   * @param {HTMLElement} resultsEl
   */
  _renderResults(actions, resultsEl) {
    if (!resultsEl) return;
    resultsEl.innerHTML = "";

    actions.forEach((action, index) => {
      const li = document.createElement("li");
      li.className = "cp-result-item";
      li.setAttribute("role", "option");
      li.setAttribute("data-action-id", action.id);
      li.setAttribute("tabindex", "-1");
      li.setAttribute("aria-selected", "false");
      li.textContent = action.label;

      li.addEventListener("mousedown", (e) => {
        // Use mousedown so it fires before the input loses focus
        e.preventDefault();
        this._focusedIndex = index;
        this.execute(action.id);
      });

      li.addEventListener("mouseover", () => {
        this._focusedIndex = index;
        this._updateFocusHighlight(resultsEl);
      });

      resultsEl.appendChild(li);
    });

    // Reset highlight
    this._updateFocusHighlight(resultsEl);
  },

  /**
   * Updates the visual focus highlight on result items.
   * @param {HTMLElement} resultsEl
   */
  _updateFocusHighlight(resultsEl) {
    if (!resultsEl) return;
    const items = resultsEl.querySelectorAll(".cp-result-item");
    items.forEach((item, i) => {
      if (i === this._focusedIndex) {
        item.classList.add("cp-result-item--focused");
        item.setAttribute("aria-selected", "true");
      } else {
        item.classList.remove("cp-result-item--focused");
        item.setAttribute("aria-selected", "false");
      }
    });
  },

  /**
   * Handles keyboard events within the palette overlay.
   * - ArrowDown / ArrowUp: move focus between results
   * - Enter: execute focused result
   * - Escape: close without executing
   * - Tab / Shift+Tab: cycle focus within the palette (focus trap)
   *
   * @param {KeyboardEvent} e
   */
  _handleKeydown(e) {
    const container = document.getElementById("command-palette-container");
    if (!container) return;

    const overlay = container.querySelector(".cp-overlay");
    if (!overlay) return;

    const input = overlay.querySelector(".cp-input");
    const resultsEl = overlay.querySelector(".cp-results");
    const items = resultsEl ? Array.from(resultsEl.querySelectorAll(".cp-result-item")) : [];

    switch (e.key) {
      case "Escape":
        e.preventDefault();
        this.close();
        break;

      case "ArrowDown":
        e.preventDefault();
        if (items.length === 0) break;
        this._focusedIndex = Math.min(this._focusedIndex + 1, items.length - 1);
        this._updateFocusHighlight(resultsEl);
        // Move DOM focus to the item so screen readers announce it
        if (items[this._focusedIndex]) items[this._focusedIndex].focus();
        break;

      case "ArrowUp":
        e.preventDefault();
        if (items.length === 0) break;
        if (this._focusedIndex <= 0) {
          // Move focus back to input
          this._focusedIndex = -1;
          this._updateFocusHighlight(resultsEl);
          if (input) input.focus();
        } else {
          this._focusedIndex -= 1;
          this._updateFocusHighlight(resultsEl);
          if (items[this._focusedIndex]) items[this._focusedIndex].focus();
        }
        break;

      case "Enter":
        e.preventDefault();
        if (this._focusedIndex >= 0 && this._currentResults[this._focusedIndex]) {
          this.execute(this._currentResults[this._focusedIndex].id);
        }
        break;

      case "Tab": {
        // Focus trap: cycle through input and result items
        const focusable = input ? [input, ...items] : items;
        if (focusable.length === 0) { e.preventDefault(); break; }

        const currentFocus = document.activeElement;
        const currentIdx = focusable.indexOf(currentFocus);

        if (e.shiftKey) {
          e.preventDefault();
          const prevIdx = currentIdx <= 0 ? focusable.length - 1 : currentIdx - 1;
          focusable[prevIdx].focus();
          // Update _focusedIndex: -1 for input, otherwise the item index
          this._focusedIndex = prevIdx === 0 ? -1 : prevIdx - 1;
          this._updateFocusHighlight(resultsEl);
        } else {
          e.preventDefault();
          const nextIdx = currentIdx >= focusable.length - 1 ? 0 : currentIdx + 1;
          focusable[nextIdx].focus();
          this._focusedIndex = nextIdx === 0 ? -1 : nextIdx - 1;
          this._updateFocusHighlight(resultsEl);
        }
        break;
      }

      default:
        break;
    }
  },
};
