const form = document.getElementById("search-form");
const input = document.getElementById("query");
const button = document.getElementById("search-btn");
const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const lawListEl = document.getElementById("law-list");
const chips = document.getElementById("chips");

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

function openLawWindow(lawId, lawName, query) {
  const params = new URLSearchParams({
    lawId,
    lawName: lawName || "",
  });
  if (query) params.set("q", query);
  const url = `/law?${params.toString()}`;
  const features = "noopener,noreferrer,width=1400,height=900";
  const win = window.open(url, `law-${lawId}`, features);
  if (!win) {
    setStatus("팝업이 차단되었습니다. 브라우저에서 팝업을 허용하거나 링크를 새 탭으로 열어 주세요.", true);
    // fallback: same-tab navigation hint via temporary link
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = `「${lawName}」 새 창에서 열기`;
    anchor.className = "fallback-link";
    statusEl.appendChild(document.createElement("br"));
    statusEl.appendChild(anchor);
  }
}

function renderLawList(laws, query) {
  if (!laws.length) {
    lawListEl.innerHTML = `<div class="empty">관련 법률을 찾지 못했습니다. 다른 키워드로 검색해 보세요.</div>`;
    return;
  }

  const statuteCount = laws.filter((l) => l.category === "법률").length;
  metaEl.hidden = false;
  metaEl.innerHTML = `
    <span>검색어 <strong>${escapeHtml(query)}</strong></span>
    <span class="pill">관련 법령 ${laws.length}건</span>
    ${statuteCount ? `<span class="pill">법률 ${statuteCount}건</span>` : ""}
    <span class="hint">법률·시행령·시행규칙 중 하나를 선택하면 새 창에서 3단으로 검색합니다</span>
  `;

  lawListEl.innerHTML = `
    <div class="law-list-head">
      <h2>관련 법령 선택</h2>
      <p class="law-list-sub">시행령·시행규칙을 골라도 대응 법률·시행령·시행규칙이 함께 3단으로 열립니다.</p>
    </div>
    <div class="law-grid">
      ${laws
        .map(
          (law) => `
          <button
            type="button"
            class="law-card"
            data-open-law
            data-law-id="${escapeHtml(law.lawId)}"
            data-law-name="${escapeHtml(law.lawName)}"
          >
            <span class="badge ${escapeHtml(law.category)}">${escapeHtml(law.category)}</span>
            <strong class="law-card-title">${escapeHtml(law.lawName)}</strong>
            <span class="law-card-meta">
              ${law.ministry ? `<span>${escapeHtml(law.ministry)}</span>` : ""}
              ${law.effectiveDate ? `<span>시행 ${escapeHtml(law.effectiveDate)}</span>` : ""}
              ${law.hitCount ? `<span>관련조문 힌트 ${law.hitCount}</span>` : ""}
            </span>
            <span class="law-card-action">새 창에서 검색 →</span>
          </button>`
        )
        .join("")}
    </div>
  `;
}

async function runSearch(query) {
  const q = query.trim();
  if (!q) return;

  button.disabled = true;
  button.textContent = "검색 중…";
  setStatus("관련 법률을 찾는 중입니다…");
  metaEl.hidden = true;
  lawListEl.innerHTML = "";

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&display=30`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "검색에 실패했습니다.");
    setStatus("");
    renderLawList(data.laws || [], data.query);
  } catch (err) {
    setStatus(err.message || "검색 중 오류가 발생했습니다.", true);
  } finally {
    button.disabled = false;
    button.textContent = "법률 찾기";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch(input.value);
});

chips.addEventListener("click", (event) => {
  const target = event.target.closest("button[data-q]");
  if (!target) return;
  input.value = target.dataset.q;
  runSearch(target.dataset.q);
});

lawListEl.addEventListener("click", (event) => {
  const card = event.target.closest("[data-open-law]");
  if (!card) return;
  openLawWindow(card.dataset.lawId, card.dataset.lawName, input.value.trim());
});

const params = new URLSearchParams(location.search);
if (params.get("q")) {
  input.value = params.get("q");
  runSearch(params.get("q"));
}
