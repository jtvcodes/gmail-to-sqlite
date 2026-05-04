// Shared attachment helpers for the Arkchive SPA.
// Loaded before messageDetail.js, messageList.js, and readingPane.js.

/**
 * Returns true for MIME types the browser can preview natively.
 *
 * @param {string|undefined} mimeType
 * @returns {boolean}
 */
function isPreviewable(mimeType) {
  if (!mimeType) return false;
  if (mimeType.startsWith("image/")) return true;
  var previewable = [
    "application/pdf",
    "text/plain",
    "text/csv",
    "text/html",
  ];
  return previewable.includes(mimeType);
}

/**
 * Returns an appropriate emoji icon for a given MIME type.
 *
 * @param {string|undefined} mimeType
 * @returns {string}
 */
function attachmentIcon(mimeType) {
  if (!mimeType) return "📎";
  if (mimeType.startsWith("image/")) return "🖼️";
  if (mimeType === "application/pdf") return "📄";
  if (mimeType.startsWith("text/")) return "📝";
  if (mimeType.includes("zip") || mimeType.includes("compressed")) return "🗜️";
  if (mimeType.includes("spreadsheet") || mimeType === "text/csv") return "📊";
  if (mimeType.includes("word") || mimeType.includes("document")) return "📝";
  return "📎";
}
