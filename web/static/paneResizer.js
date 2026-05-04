/**
 * paneResizer.js
 *
 * Makes the right and below reading panes resizable by dragging a handle.
 *
 * Right pane:  drag #rp-resize-right left/right  → changes --rp-right-width
 * Below pane:  drag #rp-resize-below up/down      → changes --rp-below-height
 *
 * Sizes are persisted to localStorage so they survive page reloads.
 * CSS handles show/hide of the handles based on data-reading-pane attribute.
 */

const paneResizer = (function () {
  const STORAGE_KEY_RIGHT = "arkchive-rp-right-width";
  const STORAGE_KEY_BELOW = "arkchive-rp-below-height";

  const RIGHT_MIN = 200;
  const RIGHT_MAX = 900;
  const BELOW_MIN = 100;
  const BELOW_MAX = 700;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function setRightWidth(px) {
    const clamped = Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, px));
    document.documentElement.style.setProperty("--rp-right-width", clamped + "px");
    try { localStorage.setItem(STORAGE_KEY_RIGHT, String(clamped)); } catch (_) {}
  }

  function setBelowHeight(px) {
    const clamped = Math.max(BELOW_MIN, Math.min(BELOW_MAX, px));
    document.documentElement.style.setProperty("--rp-below-height", clamped + "px");
    try { localStorage.setItem(STORAGE_KEY_BELOW, String(clamped)); } catch (_) {}
  }

  function restoreSizes() {
    try {
      const w = localStorage.getItem(STORAGE_KEY_RIGHT);
      if (w) document.documentElement.style.setProperty("--rp-right-width", w + "px");

      const h = localStorage.getItem(STORAGE_KEY_BELOW);
      if (h) document.documentElement.style.setProperty("--rp-below-height", h + "px");
    } catch (_) {}
  }

  function getCurrentRightWidth() {
    const val = getComputedStyle(document.documentElement)
      .getPropertyValue("--rp-right-width").trim();
    return parseInt(val, 10) || 380;
  }

  function getCurrentBelowHeight() {
    const val = getComputedStyle(document.documentElement)
      .getPropertyValue("--rp-below-height").trim();
    return parseInt(val, 10) || 320;
  }

  // ── Right handle (col-resize) ─────────────────────────────────────────────

  function initRightHandle() {
    const handle = document.getElementById("rp-resize-right");
    if (!handle) return;

    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();

      const startX = e.clientX;
      const startWidth = getCurrentRightWidth();

      handle.classList.add("dragging");
      document.body.classList.add("rp-dragging");

      function onMouseMove(ev) {
        // Moving left (negative delta) increases pane width
        const delta = startX - ev.clientX;
        setRightWidth(startWidth + delta);
      }

      function onMouseUp() {
        handle.classList.remove("dragging");
        document.body.classList.remove("rp-dragging");
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      }

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    // Double-click resets to default
    handle.addEventListener("dblclick", function () {
      setRightWidth(380);
    });
  }

  // ── Below handle (row-resize) ─────────────────────────────────────────────

  function initBelowHandle() {
    const handle = document.getElementById("rp-resize-below");
    if (!handle) return;

    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();

      const startY = e.clientY;
      const startHeight = getCurrentBelowHeight();

      handle.classList.add("dragging");
      document.body.classList.add("rp-dragging-below");

      function onMouseMove(ev) {
        // Moving up (negative delta) increases pane height
        const delta = startY - ev.clientY;
        setBelowHeight(startHeight + delta);
      }

      function onMouseUp() {
        handle.classList.remove("dragging");
        document.body.classList.remove("rp-dragging-below");
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      }

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    // Double-click resets to default
    handle.addEventListener("dblclick", function () {
      setBelowHeight(320);
    });
  }

  // ── Public init ───────────────────────────────────────────────────────────

  function init() {
    restoreSizes();
    initRightHandle();
    initBelowHandle();
  }

  return { init, setRightWidth, setBelowHeight };
}());
