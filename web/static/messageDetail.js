// Message detail component for the Gmail Web Viewer SPA
// Renders the detail panel into #message-detail.

function formatRecipient(r) {
  if (r && typeof r === 'object') {
    return r.name ? r.name + ' <' + r.email + '>' : (r.email || '');
  }
  return String(r);
}

function render() {
  const panel = document.getElementById("message-detail");

  if (!state.selectedMessage) {
    panel.setAttribute("hidden", "");
    return;
  }

  const msg = state.selectedMessage;
  panel.innerHTML = "";
  panel.removeAttribute("hidden");

  // Close button
  const closeBtn = document.createElement("button");
  closeBtn.className = "detail-close";
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", function () {
    state.selectedMessage = null;
    panel.setAttribute("hidden", "");
    state.onMessageClose();
  });
  panel.appendChild(closeBtn);

  // Subject
  const subject = document.createElement("h2");
  subject.className = "detail-subject";
  subject.textContent = msg.subject || "(no subject)";
  panel.appendChild(subject);

  // Meta block
  const meta = document.createElement("div");
  meta.className = "detail-meta";

  const sender = msg.sender || {};
  const fromLine = document.createElement("div");
  fromLine.textContent = "From: " + (sender.name || "") + " <" + (sender.email || "") + ">";
  meta.appendChild(fromLine);

  const recipients = msg.recipients || {};

  if (recipients.to && recipients.to.length > 0) {
    const toLine = document.createElement("div");
    toLine.textContent = "To: " + recipients.to.map(formatRecipient).join(", ");
    meta.appendChild(toLine);
  }

  if (recipients.cc && recipients.cc.length > 0) {
    const ccLine = document.createElement("div");
    ccLine.textContent = "Cc: " + recipients.cc.map(formatRecipient).join(", ");
    meta.appendChild(ccLine);
  }

  if (recipients.bcc && recipients.bcc.length > 0) {
    const bccLine = document.createElement("div");
    bccLine.textContent = "Bcc: " + recipients.bcc.map(formatRecipient).join(", ");
    meta.appendChild(bccLine);
  }

  const dateLine = document.createElement("div");
  dateLine.textContent = "Date: " + (msg.timestamp ? new Date(msg.timestamp).toLocaleString() : "");
  meta.appendChild(dateLine);

  // Gmail link
  const gmailLine = document.createElement("div");
  const gmailLink = document.createElement("a");
  gmailLink.href = "https://mail.google.com/mail/u/0/#all/" + msg.message_id;
  gmailLink.textContent = "Open in Gmail";
  gmailLink.target = "_blank";
  gmailLink.rel = "noopener noreferrer";
  gmailLink.className = "detail-gmail-link";
  gmailLine.appendChild(gmailLink);
  meta.appendChild(gmailLine);

  panel.appendChild(meta);

  // Labels
  const labelsDiv = document.createElement("div");
  labelsDiv.className = "detail-labels";
  (msg.labels || []).forEach(function (label) {
    const span = document.createElement("span");
    span.className = "detail-label";
    span.textContent = label;
    labelsDiv.appendChild(span);
  });
  panel.appendChild(labelsDiv);

  // Body — render in a sandboxed iframe to isolate styles
  const bodyDiv = document.createElement("div");
  bodyDiv.className = "detail-body";

  const iframe = document.createElement("iframe");
  iframe.className = "detail-body-frame";
  iframe.setAttribute("sandbox", "allow-same-origin");
  iframe.setAttribute("title", "Message body");
  bodyDiv.appendChild(iframe);
  panel.appendChild(bodyDiv);

  // Write content after appending so contentDocument is available
  const rawBody = msg.body || "";
  const isHtml = /<\s*html[\s>]/i.test(rawBody) || /<\s*(div|table|p|span|br)\b/i.test(rawBody);
  let htmlContent;
  if (isHtml) {
    htmlContent = rawBody;
  } else {
    // Plain text: escape HTML, linkify URLs, preserve line breaks
    const escaped = rawBody
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const linkified = escaped.replace(
      /(https?:\/\/[^\s]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    htmlContent = `<pre style="white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:14px;line-height:1.6;margin:0">${linkified}</pre>`;
  }

  const doc = iframe.contentDocument || iframe.contentWindow.document;
  doc.open();
  doc.write(`<!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>
      body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; color: #333; }
      a { color: #1a73e8; }
      img { max-width: 100%; }
    </style>
  </head><body>${htmlContent}</body></html>`);
  doc.close();

  // Auto-resize iframe to content height
  iframe.addEventListener("load", function () {
    iframe.style.height = iframe.contentDocument.body.scrollHeight + "px";
  });
  // Fallback resize after a short delay
  setTimeout(function () {
    if (iframe.contentDocument) {
      iframe.style.height = iframe.contentDocument.body.scrollHeight + "px";
    }
  }, 100);
}

const messageDetail = { render };
