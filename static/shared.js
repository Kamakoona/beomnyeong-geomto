/* Shared browser helpers for search / law / ordinance pages. */

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function queryTerms(query) {
  const q = (query || "").trim();
  if (!q) return [];
  const parts = q.split(/[\s,/·ㆍ]+/).filter((t) => t.length >= 2);
  const terms = [];
  const seen = new Set();
  for (const term of [q, ...parts]) {
    if (!term || seen.has(term)) continue;
    seen.add(term);
    terms.push(term);
  }
  terms.sort((a, b) => b.length - a.length);
  return terms;
}

export function highlightText(text, query) {
  const source = String(text ?? "");
  const terms = queryTerms(query);
  if (!terms.length) return escapeHtml(source);

  const escaped = escapeHtml(source);
  const pattern = terms.map(escapeRegExp).map(escapeHtml).join("|");
  if (!pattern) return escaped;

  try {
    const re = new RegExp(`(${pattern})`, "gi");
    return escaped.replace(re, `<mark class="hit">$1</mark>`);
  } catch {
    return escaped;
  }
}

export function encodeLawUrl(url) {
  const value = String(url || "");
  if (!value) return "";
  if (value.startsWith("data:") || value.startsWith("blob:")) return value;
  try {
    return encodeURI(decodeURI(value));
  } catch {
    return value;
  }
}

export function setStatus(statusEl, message, isError = false) {
  if (!statusEl) return;
  if (!message) {
    statusEl.hidden = true;
    statusEl.textContent = "";
    statusEl.classList.remove("error");
    return;
  }
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}
