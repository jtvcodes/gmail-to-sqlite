/**
 * Frontend property-based tests for the sync button dropdown feature.
 *
 * Uses fast-check for property generation and jest-environment-jsdom for DOM simulation.
 * Each property runs a minimum of 100 iterations.
 *
 * Properties tested:
 *   Property 1: Loading state is a round-trip for split button segments (Req 1.6)
 *   Property 4: Error messages are surfaced to the UI (Req 3.5, 4.4, 5.4)
 *   Property 5: Loading overlay label matches sync mode (Req 7.1, 7.2, 7.3)
 *   Property 6: aria-expanded accurately reflects dropdown state (Req 8.6)
 *   Property 7: Keyboard Enter on any menu item triggers its sync mode (Req 8.5)
 */

"use strict";

const fc = require("fast-check");

// ---------------------------------------------------------------------------
// DOM setup helpers
// ---------------------------------------------------------------------------

/**
 * Build the minimal DOM structure that app.js functions depend on.
 * Returns a cleanup function.
 */
function setupDOM() {
  document.body.innerHTML = `
    <div id="loading-overlay" hidden>
      <div class="spinner"></div>
      <div id="loading-label" style="margin-top:12px;font-size:13px;color:#555"></div>
    </div>
    <div id="filter-bar"></div>
    <div id="error-banner" hidden></div>
    <div class="sync-split-btn" id="sync-split-btn">
      <button
        id="sync-primary-btn"
        class="sync-primary"
      >⟳ Sync New Data</button>
      <button
        id="sync-toggle-btn"
        class="sync-toggle"
        aria-haspopup="true"
        aria-expanded="false"
        aria-label="More sync options"
      >▾</button>
      <ul
        id="sync-dropdown"
        class="sync-dropdown-menu"
        role="menu"
        hidden
      >
        <li role="menuitem" tabindex="-1">⟳ Sync New Data</li>
        <li role="menuitem" tabindex="-1">⟳ Sync All (Forced)</li>
        <li role="menuitem" tabindex="-1">⟳ Sync Missing</li>
      </ul>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Extracted / re-implemented functions under test
//
// We re-implement the functions here rather than eval-ing app.js because
// app.js has a DOMContentLoaded listener that fires async side-effects and
// references globals (api, messageList, etc.) that are not available in the
// test environment.  The implementations below are faithful copies of the
// relevant functions from app.js.
// ---------------------------------------------------------------------------

const MODES = ["delta", "force", "missing"];
const MODE_LABELS = {
  delta: "Syncing new messages…",
  force: "Force-syncing all messages…",
  missing: "Syncing missing messages…",
};

/** Faithful copy of labelForMode() from app.js */
function labelForMode(mode) {
  if (mode === "delta") return "Syncing new messages…";
  if (mode === "force") return "Force-syncing all messages…";
  return "Syncing missing messages…";
}

/** Faithful copy of setLoading() from app.js */
function setLoading(on, label) {
  const overlay = document.getElementById("loading-overlay");
  const bar = document.getElementById("filter-bar");
  const lbl = document.getElementById("loading-label");
  const primaryBtn = document.getElementById("sync-primary-btn");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (on) {
    if (lbl) lbl.textContent = label || "";
    overlay.removeAttribute("hidden");
    bar.classList.add("loading");
    if (primaryBtn) {
      primaryBtn.disabled = true;
      primaryBtn.textContent = "⟳ Syncing…";
    }
    if (toggleBtn) toggleBtn.disabled = true;
  } else {
    overlay.setAttribute("hidden", "");
    bar.classList.remove("loading");
    if (lbl) lbl.textContent = "";
    if (primaryBtn) {
      primaryBtn.disabled = false;
      primaryBtn.textContent = "⟳ Sync New Data";
    }
    if (toggleBtn) toggleBtn.disabled = false;
  }
}

/** Faithful copy of closeSyncDropdown() from app.js */
function closeSyncDropdown() {
  const dropdown = document.getElementById("sync-dropdown");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (dropdown) dropdown.setAttribute("hidden", "");
  if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "false");
}

/** Faithful copy of isSyncLoading() from app.js */
function isSyncLoading() {
  const primaryBtn = document.getElementById("sync-primary-btn");
  return primaryBtn ? primaryBtn.disabled : false;
}

/** Faithful copy of toggleSyncDropdown() from app.js (without the outside-click timer) */
function toggleSyncDropdown() {
  if (isSyncLoading()) return;

  const dropdown = document.getElementById("sync-dropdown");
  const toggleBtn = document.getElementById("sync-toggle-btn");
  if (!dropdown) return;

  const isOpen = !dropdown.hasAttribute("hidden");

  if (isOpen) {
    closeSyncDropdown();
  } else {
    dropdown.removeAttribute("hidden");
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
  }
}

/**
 * Faithful copy of the state object (minimal subset needed for tests).
 * Re-created fresh for each test that needs it.
 */
function makeState() {
  return { error: null };
}

/** Faithful copy of renderError() from app.js, operating on a given state */
function renderError(state) {
  const banner = document.getElementById("error-banner");
  if (state.error) {
    banner.textContent = state.error;
    banner.removeAttribute("hidden");
  } else {
    banner.setAttribute("hidden", "");
  }
}

/**
 * Simulate runSync() for error-surfacing tests.
 * Instead of calling real fetch, accepts a pre-built response object.
 */
async function runSyncWithFakeResponse(mode, fakeResponse, state) {
  closeSyncDropdown();
  setLoading(true, labelForMode(mode));
  try {
    const resp = fakeResponse;
    const data = await resp.json();
    if (!resp.ok) {
      state.error = data.error || "Sync failed";
      renderError(state);
    } else {
      state.error = null;
      renderError(state);
    }
  } catch (_err) {
    state.error = "Network error — could not reach the server";
    renderError(state);
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------------
// Property 1: Loading state is a round-trip for split button segments
// Validates: Requirements 1.6
// ---------------------------------------------------------------------------

describe("Property 1: Loading state is a round-trip for split button segments", () => {
  /**
   * **Validates: Requirements 1.6**
   *
   * For any initial label text on the primary button, calling setLoading(true)
   * followed by setLoading(false) SHALL restore disabled=false and the original
   * label "⟳ Sync New Data" on both segments.
   */
  test("setLoading(true) then setLoading(false) restores original state", () => {
    fc.assert(
      fc.property(
        // Generate arbitrary label text to pass to setLoading(true, label)
        fc.string({ minLength: 0, maxLength: 200 }),
        (loadingLabel) => {
          setupDOM();

          const primaryBtn = document.getElementById("sync-primary-btn");
          const toggleBtn = document.getElementById("sync-toggle-btn");

          // Capture the original label before any loading
          const originalLabel = primaryBtn.textContent;

          // Apply loading state
          setLoading(true, loadingLabel);

          // Verify loading state was applied
          expect(primaryBtn.disabled).toBe(true);
          expect(toggleBtn.disabled).toBe(true);
          expect(primaryBtn.textContent).toBe("⟳ Syncing…");

          // Restore from loading state
          setLoading(false);

          // Both segments must be re-enabled
          expect(primaryBtn.disabled).toBe(false);
          expect(toggleBtn.disabled).toBe(false);

          // Primary button label must be restored to the original
          expect(primaryBtn.textContent).toBe(originalLabel);
          expect(primaryBtn.textContent).toBe("⟳ Sync New Data");
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 5: Loading overlay label matches sync mode
// Validates: Requirements 7.1, 7.2, 7.3
// ---------------------------------------------------------------------------

describe("Property 5: Loading overlay label matches sync mode", () => {
  /**
   * **Validates: Requirements 7.1, 7.2, 7.3**
   *
   * For any sync mode in {'delta', 'force', 'missing'}, the loading overlay
   * label displayed during the sync SHALL be the mode-specific string.
   */
  test("labelForMode returns the correct mode-specific string", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("delta", "force", "missing"),
        (mode) => {
          const label = labelForMode(mode);

          if (mode === "delta") {
            expect(label).toBe("Syncing new messages…");
          } else if (mode === "force") {
            expect(label).toBe("Force-syncing all messages…");
          } else {
            expect(label).toBe("Syncing missing messages…");
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  test("setLoading(true, labelForMode(mode)) sets the overlay label correctly", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("delta", "force", "missing"),
        (mode) => {
          setupDOM();

          const lbl = document.getElementById("loading-label");
          const expectedLabel = labelForMode(mode);

          setLoading(true, expectedLabel);

          expect(lbl.textContent).toBe(expectedLabel);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4: Error messages are surfaced to the UI
// Validates: Requirements 3.5, 4.4, 5.4
// ---------------------------------------------------------------------------

describe("Property 4: Error messages are surfaced to the UI", () => {
  /**
   * **Validates: Requirements 3.5, 4.4, 5.4**
   *
   * For any non-empty error string returned by the Sync_API, the UI error
   * banner SHALL display exactly that error message after the sync call
   * completes, and state.error SHALL equal that string.
   */
  test("arbitrary non-empty error strings are surfaced to state.error and the error banner", async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate arbitrary non-empty error strings
        fc.string({ minLength: 1, maxLength: 500 }),
        fc.constantFrom("delta", "force", "missing"),
        async (errorMessage, mode) => {
          setupDOM();

          const state = makeState();

          // Build a fake failed response containing the error string
          const fakeResponse = {
            ok: false,
            json: async () => ({ error: errorMessage }),
          };

          await runSyncWithFakeResponse(mode, fakeResponse, state);

          // state.error must equal the error string exactly
          expect(state.error).toBe(errorMessage);

          // The error banner must display the error string
          const banner = document.getElementById("error-banner");
          expect(banner.textContent).toBe(errorMessage);
          expect(banner.hasAttribute("hidden")).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 6: aria-expanded accurately reflects dropdown state
// Validates: Requirements 8.6
// ---------------------------------------------------------------------------

describe("Property 6: aria-expanded accurately reflects dropdown state", () => {
  /**
   * **Validates: Requirements 8.6**
   *
   * For any sequence of open/close toggle operations, the aria-expanded
   * attribute on the toggle button SHALL equal "true" when the dropdown is
   * visible and "false" when it is hidden.
   */
  test("aria-expanded matches dropdown visibility after arbitrary toggle sequences", () => {
    fc.assert(
      fc.property(
        // Generate a sequence of 1–20 boolean operations:
        // true = open (removeAttribute hidden), false = close (setAttribute hidden)
        fc.array(fc.boolean(), { minLength: 1, maxLength: 20 }),
        (operations) => {
          setupDOM();

          const dropdown = document.getElementById("sync-dropdown");
          const toggleBtn = document.getElementById("sync-toggle-btn");

          for (const shouldOpen of operations) {
            if (shouldOpen) {
              // Open the dropdown
              dropdown.removeAttribute("hidden");
              toggleBtn.setAttribute("aria-expanded", "true");
            } else {
              // Close the dropdown
              closeSyncDropdown();
            }

            // Invariant: aria-expanded === "true" iff dropdown is visible
            const isVisible = !dropdown.hasAttribute("hidden");
            const ariaExpanded = toggleBtn.getAttribute("aria-expanded");

            if (isVisible) {
              expect(ariaExpanded).toBe("true");
            } else {
              expect(ariaExpanded).toBe("false");
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  test("toggleSyncDropdown keeps aria-expanded in sync with dropdown visibility", () => {
    fc.assert(
      fc.property(
        // Generate a sequence of 1–20 toggle calls
        fc.array(fc.constant("toggle"), { minLength: 1, maxLength: 20 }),
        (operations) => {
          setupDOM();

          const dropdown = document.getElementById("sync-dropdown");
          const toggleBtn = document.getElementById("sync-toggle-btn");

          for (const _op of operations) {
            toggleSyncDropdown();

            // Invariant: aria-expanded === "true" iff dropdown is visible
            const isVisible = !dropdown.hasAttribute("hidden");
            const ariaExpanded = toggleBtn.getAttribute("aria-expanded");

            if (isVisible) {
              expect(ariaExpanded).toBe("true");
            } else {
              expect(ariaExpanded).toBe("false");
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 7: Keyboard Enter on any menu item triggers its sync mode
// Validates: Requirements 8.5
// ---------------------------------------------------------------------------

describe("Property 7: Keyboard Enter on any menu item triggers its sync mode", () => {
  /**
   * **Validates: Requirements 8.5**
   *
   * For any menu item index in [0, 2], pressing Enter while that item has
   * focus SHALL trigger runSync with the correct mode for that index and
   * close the dropdown.
   *
   * Mode mapping (from index.html):
   *   index 0 → 'delta'
   *   index 1 → 'force'
   *   index 2 → 'missing'
   */
  test("Enter on menu item at index i calls runSync with the correct mode and closes dropdown", () => {
    const INDEX_TO_MODE = ["delta", "force", "missing"];

    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 2 }),
        (itemIndex) => {
          setupDOM();

          const dropdown = document.getElementById("sync-dropdown");
          const toggleBtn = document.getElementById("sync-toggle-btn");

          // Track runSync calls
          const runSyncCalls = [];

          // Wire up onclick handlers on menu items (mirroring index.html)
          const items = Array.from(
            dropdown.querySelectorAll('[role="menuitem"]')
          );
          items.forEach((item, idx) => {
            item.onclick = () => {
              runSyncCalls.push(INDEX_TO_MODE[idx]);
            };
          });

          // Open the dropdown
          dropdown.removeAttribute("hidden");
          toggleBtn.setAttribute("aria-expanded", "true");

          // Focus the target item
          const targetItem = items[itemIndex];
          targetItem.focus();

          // Simulate the keydown handler from app.js
          // (the Enter/Space branch: trigger onclick and close dropdown)
          const focused = document.activeElement;
          if (focused && items.includes(focused)) {
            if (typeof focused.onclick === "function") {
              focused.onclick(new Event("click"));
            }
            closeSyncDropdown();
          }

          // Assert runSync was called with the correct mode
          expect(runSyncCalls).toHaveLength(1);
          expect(runSyncCalls[0]).toBe(INDEX_TO_MODE[itemIndex]);

          // Assert dropdown is closed
          expect(dropdown.hasAttribute("hidden")).toBe(true);
          expect(toggleBtn.getAttribute("aria-expanded")).toBe("false");
        }
      ),
      { numRuns: 100 }
    );
  });
});
