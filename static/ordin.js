const params = new URLSearchParams(location.search);
const initialQuery = (params.get("q") || "").trim();

const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const listEl = document.getElementById("ordin-list");
const pageTitle = document.getElementById("page-title");
const scopeLead = document.getElementById("scope-lead");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(message, isError = false) {
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

function renderList(items, query) {
  pageTitle.textContent = `「${query}」 자치법규`;
  document.title = `${query} · 자치법규`;
  scopeLead.innerHTML = `
    검색어 <em>${escapeHtml(query)}</em>가 포함된 자치법규 ${items.length}건입니다.
    카드를 누르면 원문이 새 탭에서 열립니다.
  `;

  metaEl.hidden = false;
  metaEl.innerHTML = `
    <span>검색어 <strong>${escapeHtml(query)}</strong></span>
    <span class="pill">자치법규 ${items.length}건</span>
  `;

  if (!items.length) {
    listEl.innerHTML = `<div class="empty">일치하는 자치법규가 없습니다.</div>`;
    return;
  }

  listEl.innerHTML = `
    <div class="law-list-head">
      <h2>자치법규 선택</h2>
      <p class="law-list-sub">원문은 국가법령정보센터에서 새 탭으로 열립니다.</p>
    </div>
    <div class="law-grid">
      ${items
        .map((item) => {
          const href = item.sourceUrl || item.detailUrl || "";
          return `
        <a
          class="law-card"
          href="${escapeHtml(href)}"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span class="badge 자치법규">자치법규</span>
          <strong class="law-card-title">${escapeHtml(item.ordinName || "")}</strong>
          <span class="law-card-meta">
            ${item.orgName ? `<span>${escapeHtml(item.orgName)}</span>` : ""}
            ${item.effectiveDate ? `<span>시행 ${escapeHtml(item.effectiveDate)}</span>` : ""}
          </span>
          <span class="law-card-action">원문 새 탭 →</span>
        </a>`;
        })
        .join("")}
    </div>
  `;
}

async function loadOrdinances(query) {
  const q = query.trim();
  if (!q) {
    setStatus("검색어가 없습니다.", true);
    return;
  }

  setStatus("자치법규를 검색하는 중입니다…");
  try {
    const res = await fetch(`/api/ordinances?q=${encodeURIComponent(q)}&display=50`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "자치법규 검색에 실패했습니다.");
    setStatus("");
    renderList(data.ordinances || [], data.query || q);
  } catch (err) {
    setStatus(err.message || "자치법규 검색 중 오류가 발생했습니다.", true);
  }
}

if (initialQuery) {
  loadOrdinances(initialQuery);
} else {
  setStatus("검색어(q)가 없습니다. 메인에서 다시 검색해 주세요.", true);
}
