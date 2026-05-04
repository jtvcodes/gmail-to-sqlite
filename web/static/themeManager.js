// Theme Manager and Density Manager for the Arkchive SPA
// Manages light/dark theme and cozy/compact density preferences.
// Persists preferences to localStorage and applies them via data attributes on <html>.
//
// Depends on the global `state` object defined in app.js.

const themeManager = {
  STORAGE_KEY_THEME: "arkchive-theme",
  STORAGE_KEY_DENSITY: "arkchive-density",

  /**
   * Initialise theme and density from persisted preferences or OS defaults.
   * - Theme: reads localStorage["arkchive-theme"]; falls back to prefers-color-scheme.
   * - Density: reads localStorage["arkchive-density"]; falls back to "cozy".
   * All localStorage access is wrapped in try/catch to handle private-browsing mode
   * or storage-full errors gracefully.
   */
  init() {
    // --- Theme ---
    let storedTheme = null;
    try {
      storedTheme = localStorage.getItem(this.STORAGE_KEY_THEME);
    } catch (_) {
      // localStorage unavailable — fall through to OS preference
    }

    let theme;
    if (storedTheme === "light" || storedTheme === "dark") {
      theme = storedTheme;
    } else {
      // No stored preference — default to dark and persist it immediately
      theme = "dark";
      try {
        localStorage.setItem(this.STORAGE_KEY_THEME, "dark");
      } catch (_) {}
    }

    // --- Density ---
    let storedDensity = null;
    try {
      storedDensity = localStorage.getItem(this.STORAGE_KEY_DENSITY);
    } catch (_) {
      // localStorage unavailable — fall through to default
    }

    const density =
      storedDensity === "cozy" || storedDensity === "compact"
        ? storedDensity
        : "cozy";

    this.applyTheme(theme);
    this.applyDensity(density);
  },

  /**
   * Apply a theme by setting data-theme on <html>, updating state.theme,
   * and persisting to localStorage.
   * Must complete within 50 ms.
   *
   * @param {"light"|"dark"} theme
   */
  applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);

    // Update shared state if available
    if (typeof state !== "undefined") {
      state.theme = theme;
    }

    // Update the toggle button icon: moon (active/colored) in dark, sun in light
    const btn = document.getElementById("theme-toggle-btn");
    if (btn) {
      btn.textContent = theme === "dark" ? "🌙" : "☀";
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
      btn.setAttribute("title", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
      btn.dataset.active = theme === "dark" ? "true" : "false";
    }

    try {
      localStorage.setItem(this.STORAGE_KEY_THEME, theme);
    } catch (_) {
      // Storage unavailable — preference not persisted, but UI is updated
    }
  },

  /**
   * Toggle between "light" and "dark" themes.
   */
  toggleTheme() {
    const current =
      typeof state !== "undefined" ? state.theme : null;
    const currentAttr = document.documentElement.getAttribute("data-theme");
    const active = current || currentAttr || "light";
    this.applyTheme(active === "dark" ? "light" : "dark");
  },

  /**
   * Apply a density mode by setting data-density on <html>, updating state.density,
   * and persisting to localStorage.
   * Must complete within 50 ms.
   *
   * @param {"cozy"|"compact"} density
   */
  applyDensity(density) {
    document.documentElement.setAttribute("data-density", density);

    // Update shared state if available
    if (typeof state !== "undefined") {
      state.density = density;
    }

    try {
      localStorage.setItem(this.STORAGE_KEY_DENSITY, density);
    } catch (_) {
      // Storage unavailable — preference not persisted, but UI is updated
    }
  },

  /**
   * Toggle between "cozy" and "compact" density modes.
   */
  toggleDensity() {
    const current =
      typeof state !== "undefined" ? state.density : null;
    const currentAttr = document.documentElement.getAttribute("data-density");
    const active = current || currentAttr || "cozy";
    this.applyDensity(active === "compact" ? "cozy" : "compact");
  },
};
