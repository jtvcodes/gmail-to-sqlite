// Log Console — modal window that captures and displays app log output.
// Intercepts console.log / console.warn / console.error and also exposes
// logConsole.append(line) for direct writes (e.g. from sync stream output).

const logConsole = (() => {
  const MAX_LINES = 2000;
  const _lines = [];
  let _open = false;

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  function _output() {
    return document.getElementById("log-console-output");
  }

  function _overlay() {
    return document.getElementById("log-console-overlay");
  }

  function _scrollToBottom() {
    const el = _output();
    if (el) el.scrollTop = el.scrollHeight;
  }

  function _flush() {
    const el = _output();
    if (!el) return;
    el.textContent = _lines.join("\n");
    _scrollToBottom();
  }

  function _addLine(level, args) {
    const ts = new Date().toISOString().replace("T", " ").slice(0, 23);
    const msg = args.map(a => {
      if (typeof a === "string") return a;
      try { return JSON.stringify(a); } catch (_) { return String(a); }
    }).join(" ");
    const line = `[${ts}] [${level.toUpperCase()}] ${msg}`;

    _lines.push(line);
    if (_lines.length > MAX_LINES) _lines.shift();

    if (_open) {
      const el = _output();
      if (el) {
        // Append incrementally — faster than full re-render
        const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        el.textContent = _lines.join("\n");
        if (atBottom) _scrollToBottom();
      }
    }
  }

  // -------------------------------------------------------------------------
  // Intercept console methods
  // -------------------------------------------------------------------------

  const _origLog   = console.log.bind(console);
  const _origWarn  = console.warn.bind(console);
  const _origError = console.error.bind(console);

  console.log = function (...args) {
    _origLog(...args);
    _addLine("log", args);
  };
  console.warn = function (...args) {
    _origWarn(...args);
    _addLine("warn", args);
  };
  console.error = function (...args) {
    _origError(...args);
    _addLine("error", args);
  };

  // -------------------------------------------------------------------------
  // Keyboard: Escape closes the modal
  // -------------------------------------------------------------------------

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && _open) logConsole.close();
  });

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  return {
    /** Append a raw line directly (e.g. sync stream output). */
    append(line) {
      _addLine("log", [line]);
    },

    /** Open the log console modal. */
    open() {
      const overlay = _overlay();
      if (!overlay) return;
      _open = true;
      overlay.removeAttribute("hidden");
      _flush();
      // Focus the output for keyboard scrolling
      const el = _output();
      if (el) { el.setAttribute("tabindex", "-1"); el.focus(); }
      // Close when clicking the backdrop (outside the modal card)
      setTimeout(() => {
        overlay.addEventListener("click", function onBackdrop(e) {
          if (e.target === overlay) {
            logConsole.close();
            overlay.removeEventListener("click", onBackdrop);
          }
        });
      }, 0);
    },

    /** Close the log console modal. */
    close() {
      const overlay = _overlay();
      if (!overlay) return;
      _open = false;
      overlay.setAttribute("hidden", "");
      // Return focus to the button that opened it
      const btn = document.getElementById("log-console-btn");
      if (btn) btn.focus();
    },

    /** Clear all log lines. */
    clear() {
      _lines.length = 0;
      const el = _output();
      if (el) el.textContent = "";
    },

    /** Returns all captured lines (for external use). */
    getLines() {
      return [..._lines];
    },
  };
})();
