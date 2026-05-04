/**
 * Toast Manager
 * Manages a queue of toast notifications rendered in #toast-container.
 * Up to 3 toasts are visible at once; additional toasts queue in FIFO order.
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 11.4
 */

const toastManager = {
  /** @type {Array<{id: string, type: "success"|"error", message: string, autoDismiss: boolean}>} */
  _queue: [],

  /**
   * Returns a unique ID for a toast.
   * Uses crypto.randomUUID() if available, otherwise falls back to Date.now() + Math.random().
   * @returns {string}
   */
  _generateId() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  },

  /**
   * Creates a success toast that auto-dismisses after 3000ms.
   * @param {string} message
   * @returns {{id: string, type: "success", message: string, autoDismiss: boolean}}
   */
  success(message) {
    const toast = {
      id: this._generateId(),
      type: "success",
      message,
      autoDismiss: true,
    };
    this._queue.push(toast);
    this._render();
    setTimeout(() => {
      this.dismiss(toast.id);
    }, 3000);
    return toast;
  },

  /**
   * Creates an error toast that persists until manually dismissed.
   * @param {string} message
   * @returns {{id: string, type: "error", message: string, autoDismiss: boolean}}
   */
  error(message) {
    const toast = {
      id: this._generateId(),
      type: "error",
      message,
      autoDismiss: false,
    };
    this._queue.push(toast);
    this._render();
    return toast;
  },

  /**
   * Dismisses a toast by ID with a 200ms fade-out animation.
   * @param {string} toastId
   */
  dismiss(toastId) {
    const container = document.getElementById("toast-container");
    if (container) {
      const el = container.querySelector(`[data-toast-id="${CSS.escape(toastId)}"]`);
      if (el) {
        el.classList.add("toast--dismissing");
        setTimeout(() => {
          el.remove();
          // After removing the element, render any queued toasts that weren't visible
          this._renderQueued();
        }, 200);
      }
    }
    // Remove from internal queue immediately
    this._queue = this._queue.filter((t) => t.id !== toastId);
  },

  /**
   * Renders up to 3 toasts in #toast-container.
   * Only toasts not already rendered are added.
   */
  _render() {
    const container = document.getElementById("toast-container");
    if (!container) return;

    // Count currently visible (non-dismissing) toasts
    const visibleEls = container.querySelectorAll(".toast:not(.toast--dismissing)");
    const visibleIds = new Set(
      Array.from(visibleEls).map((el) => el.getAttribute("data-toast-id"))
    );

    // Determine how many slots are available (max 3 visible at once)
    const slotsAvailable = 3 - visibleEls.length;
    if (slotsAvailable <= 0) return;

    // Find queued toasts not yet rendered
    const toRender = this._queue
      .filter((t) => !visibleIds.has(t.id))
      .slice(0, slotsAvailable);

    for (const toast of toRender) {
      const el = this._createToastElement(toast);
      container.appendChild(el);
    }
  },

  /**
   * Re-renders queued toasts after a dismissal frees up a slot.
   * Called after the fade-out animation completes.
   */
  _renderQueued() {
    this._render();
  },

  /**
   * Creates a DOM element for a toast.
   * @param {{id: string, type: "success"|"error", message: string, autoDismiss: boolean}} toast
   * @returns {HTMLElement}
   */
  _createToastElement(toast) {
    const el = document.createElement("div");
    el.className = `toast toast--${toast.type}`;
    el.setAttribute("data-toast-id", toast.id);
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");

    const msgSpan = document.createElement("span");
    msgSpan.className = "toast__message";
    msgSpan.textContent = toast.message;

    const dismissBtn = document.createElement("button");
    dismissBtn.className = "toast__dismiss";
    dismissBtn.setAttribute("aria-label", "Dismiss notification");
    dismissBtn.textContent = "✕";
    dismissBtn.addEventListener("click", () => {
      this.dismiss(toast.id);
    });

    el.appendChild(msgSpan);
    el.appendChild(dismissBtn);

    return el;
  },
};
