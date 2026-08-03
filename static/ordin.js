const params = new URLSearchParams(location.search);
const initialQuery = (params.get("q") || "").trim();
const initialMst = (params.get("mst") || "").trim();
const initialName = (params.get("name") || params.get("ordinName") || "").trim();

const form = document.getElementById("search-form");
const input = document.getElementById("query");
const button = document.getElementById("search-btn");
const openAllBtn = document.getElementById("open-all-btn");
const searchBar = document.getElementById("search-bar");
const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const compareEl = document.getElementById("compare");
const listEl = document.getElementById("ordin-list");
const pageTitle = document.getElementById("page-title");
const scopePill = document.getElementById("scope-pill");
const scopeLead = document.getElementById("scope-lead");
const workspaceEl = document.getElementById("workspace");

function setOpenAllVisible(visible) {
  if (!openAllBtn) return;
  openAllBtn.hidden = !visible;
  searchBar?.classList.toggle("with-secondary", Boolean(visible));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function queryTerms(query) {
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

function highlightText(text, query) {
  const source = String(text ?? "");
  const terms = queryTerms(query);
  if (!terms.length) return escapeHtml(source);
  const escaped = escapeHtml(source);
  const pattern = terms.map(escapeRegExp).map(escapeHtml).join("|");
  if (!pattern) return escaped;
  return escaped.replace(new RegExp(`(${pattern})`, "gi"), '<mark class="hit">$1</mark>');
}

function encodeLawUrl(url) {
  const value = String(url || "");
  if (!value) return "";
  try {
    return encodeURI(decodeURI(value));
  } catch {
    return value;
  }
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

function syncUrl({ query = currentQuery, mst = currentMst, name = currentName, mode = "" } = {}) {
  const next = new URL(location.href);
  next.searchParams.set("q", query || "");
  if (mst) next.searchParams.set("mst", mst);
  else next.searchParams.delete("mst");
  if (name) next.searchParams.set("name", name);
  else next.searchParams.delete("name");
  if (mode === "full") next.searchParams.set("mode", "full");
  else next.searchParams.delete("mode");
  history.replaceState(null, "", next);
}

function articleCard(article, query) {
  const titleRaw = article.articleTitle
    ? `${article.articleLabel}(${article.articleTitle})`
    : article.articleLabel;
  const detailUrl = encodeLawUrl(article.detailUrl);
  return `
    <article class="tri-article is-compact">
      <div class="tri-article-head">
        <span class="article-label">${highlightText(titleRaw, query)}</span>
      </div>
      <div class="article-body">${highlightText(article.articleContent || "", query)}</div>
      <div class="article-meta">
        ${article.effectiveDate ? `<span>시행 ${escapeHtml(article.effectiveDate)}</span>` : ""}
        <a
          href="${escapeHtml(detailUrl)}"
          class="source-open"
          target="_blank"
          rel="noopener noreferrer"
        >원문</a>
      </div>
    </article>
  `;
}

function renderArticles(data) {
  const instrument = data.instrument || {};
  const articles = Array.isArray(data.articles) ? data.articles : [];
  const isFull = data.mode === "full";
  const query = isFull ? "" : data.query || currentQuery;
  const name = instrument.ordinName || currentName || "선택한 자치법규";

  currentMst = instrument.mst || currentMst;
  currentName = name;
  currentQuery = isFull ? currentQuery : query;
  setOpenAllVisible(Boolean(currentMst));

  pageTitle.textContent = isFull ? `${name} · 전체 조문` : name;
  document.title = isFull ? `${name} · 전체 조문` : `${name} · 자치법규 검색`;

  workspaceEl.hidden = false;
  listEl.hidden = true;

  scopePill.hidden = false;
  scopePill.style.gridTemplateColumns = "1fr";
  scopePill.innerHTML = `
    <div class="scope-item" data-cat="자치법규">
      <div class="scope-item-top">
        <span class="badge 자치법규">자치법규</span>
      </div>
      <div class="scope-item-body">
        <strong>${escapeHtml(name)}</strong>
        <span class="scope-date">
          ${instrument.orgName ? `${escapeHtml(instrument.orgName)} · ` : ""}
          ${
            instrument.effectiveDate
              ? `시행 ${escapeHtml(instrument.effectiveDate)}`
              : "시행일 정보 없음"
          }
        </span>
      </div>
    </div>
  `;

  metaEl.hidden = false;
  metaEl.innerHTML = `
    <div class="query-banner">
      <span class="query-banner-label">${isFull ? "보기" : "검색어"}</span>
      <strong class="query-banner-text">${escapeHtml(isFull ? "전체 조문" : query)}</strong>
    </div>
    <span class="pill">${isFull ? "전체 조문" : "관련 조문"} ${data.total || 0}건</span>
    <span class="pill">자치법규</span>
    <button type="button" class="ghost-btn" data-back-list>목록으로</button>
  `;

  if (!articles.length) {
    compareEl.innerHTML = `
      <div class="compare-toolbar">
        <div>
          <p class="compare-kicker">선택 자치법규 · ${isFull ? "전체 조문" : "키워드 일치 조문"}</p>
          <h2>「${escapeHtml(name)}」</h2>
        </div>
      </div>
      <div class="empty">${isFull ? "조문을 찾지 못했습니다." : "키워드와 일치하는 조문이 없습니다."}</div>
    `;
    return;
  }

  compareEl.innerHTML = `
    <div class="compare-toolbar">
      <div>
        <p class="compare-kicker">선택 자치법규 · ${isFull ? "전체 조문" : "키워드 일치 조문"}</p>
        <h2>「${escapeHtml(name)}」 ${isFull ? "전체 조문" : "관련 조문"}</h2>
        <p class="compare-sub">
          ${
            isFull
              ? "선택한 자치법규의 전체 조문을 표시합니다."
              : `노란색 표시는 검색어 <mark class="hit inline-hit">${escapeHtml(query)}</mark> 와 일치하는 부분입니다.`
          }
        </p>
      </div>
    </div>
    <div class="tri-grid" style="grid-template-columns: 1fr">
      <section class="tri-col" data-cat="자치법규">
        <header class="tri-col-head">
          <div>
            <p class="tri-cat">자치법규</p>
            <h3>${escapeHtml(name)}</h3>
            <p class="tri-date">
              ${
                instrument.effectiveDate
                  ? `시행 ${escapeHtml(instrument.effectiveDate)}`
                  : "시행일 정보 없음"
              }
            </p>
          </div>
          <span class="count">${articles.length}개</span>
        </header>
        <div class="tri-col-body">
          ${articles.map((a) => articleCard(a, query)).join("")}
        </div>
      </section>
    </div>
  `;
}

function markListReady() {
  if (listEl) listEl.dataset.ready = "1";
}

function renderList(items, query) {
  latestList = items;
  markListReady();
  pageTitle.textContent = `「${query}」 자치법규`;
  document.title = `${query} · 자치법규`;
  if (scopeLead) {
    scopeLead.innerHTML = `
    검색어 <em>${escapeHtml(query)}</em>가 포함된 자치법규 ${items.length}건입니다.
    항목을 선택하면 법률 3단 검색과 같은 형태로 관련 조문을 보여 줍니다.
  `;
  }
  scopePill.hidden = true;
  scopePill.innerHTML = "";
  setOpenAllVisible(false);
  workspaceEl.hidden = true;
  listEl.hidden = false;

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
      <p class="law-list-sub">선택하면 이 창에서 관련 조문을 법률 검색 결과와 같은 형태로 엽니다.</p>
    </div>
    <div class="law-grid">
      ${items
        .map(
          (item) => `
        <button
          type="button"
          class="law-card"
          data-open-ordin
          data-mst="${escapeHtml(item.mst || "")}"
          data-name="${escapeHtml(item.ordinName || "")}"
        >
          <span class="badge 자치법규">자치법규</span>
          <strong class="law-card-title">${escapeHtml(item.ordinName || "")}</strong>
          <span class="law-card-meta">
            ${item.orgName ? `<span>${escapeHtml(item.orgName)}</span>` : ""}
            ${item.effectiveDate ? `<span>시행 ${escapeHtml(item.effectiveDate)}</span>` : ""}
          </span>
          <span class="law-card-action">조문 보기 →</span>
        </button>`
        )
        .join("")}
    </div>
  `;
}

async function loadOrdinanceArticles({ query, mst, name, full = false } = {}) {
  const q = String(query || "").trim();
  const id = String(mst || "").trim();
  if (!id) return;
  if (!full && !q) return;

  currentMst = id;
  currentName = name || currentName;
  currentQuery = q || currentQuery;
  input.value = currentQuery;

  button.disabled = true;
  button.textContent = "검색 중…";
  setStatus(
    full
      ? `「${currentName || "선택 자치법규"}」 전체 조문을 불러오는 중입니다…`
      : `「${currentName || "선택 자치법규"}」에서 조문을 찾는 중입니다…`
  );
  workspaceEl.hidden = false;
  listEl.hidden = true;
  compareEl.innerHTML = `<div class="empty">조문을 불러오는 중…</div>`;
  syncUrl({ query: currentQuery, mst: currentMst, name: currentName, mode: full ? "full" : "" });

  try {
    const searchParams = new URLSearchParams({
      mst: currentMst,
      ordinName: currentName || "",
      maxArticles: full ? "300" : "80",
      mode: full ? "full" : "search",
    });
    if (!full) searchParams.set("q", currentQuery);
    const res = await fetch(`/api/ordin-compare?${searchParams}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "조문 검색에 실패했습니다.");
    setStatus("");
    renderArticles(data);
  } catch (err) {
    setStatus(err.message || "조문 검색 중 오류가 발생했습니다.", true);
    compareEl.innerHTML = `<div class="empty error-box">조문을 불러오지 못했습니다.</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "조문 검색";
  }
}

async function loadOrdinanceList(query) {
  const q = query.trim();
  if (!q) {
    setStatus("검색어가 없습니다.", true);
    return;
  }
  currentQuery = q;
  input.value = q;
  setStatus("자치법규를 검색하는 중입니다…");
  try {
    const res = await fetch(`/api/ordinances?q=${encodeURIComponent(q)}&display=50`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "자치법규 검색에 실패했습니다.");
    setStatus("");
    const items = data.ordinances || [];
    renderList(items, data.query || q);

    if (currentMst) {
      const hit = items.find((item) => String(item.mst) === String(currentMst));
      await loadOrdinanceArticles({
        query: q,
        mst: currentMst,
        name: hit?.ordinName || currentName,
      });
    }
  } catch (err) {
    setStatus(err.message || "자치법규 검색 중 오류가 발생했습니다.", true);
  }
}

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  if (currentMst) {
    loadOrdinanceArticles({ query: q, mst: currentMst, name: currentName });
  } else {
    loadOrdinanceList(q);
  }
});

openAllBtn?.addEventListener("click", () => {
  if (!currentMst) return;
  loadOrdinanceArticles({ query: currentQuery, mst: currentMst, name: currentName, full: true });
});

listEl?.addEventListener("click", (event) => {
  const card = event.target.closest("[data-open-ordin]");
  if (!card) return;
  loadOrdinanceArticles({
    query: currentQuery || input.value.trim(),
    mst: card.dataset.mst,
    name: card.dataset.name,
  });
});

metaEl?.addEventListener("click", (event) => {
  const back = event.target.closest("[data-back-list]");
  if (!back) return;
  currentMst = "";
  currentName = "";
  syncUrl({ query: currentQuery, mst: "", name: "" });
  renderList(latestList, currentQuery);
});

try {
  if (initialQuery) {
    if (input) input.value = initialQuery;
    setStatus("자치법규를 검색하는 중입니다…");
    loadOrdinanceList(initialQuery);
  } else {
    setStatus("검색어(q)가 없습니다. 메인에서 다시 검색해 주세요.", true);
  }
} catch (err) {
  setStatus(err?.message || "화면을 초기화하지 못했습니다.", true);
  console.error(err);
}

window.__ordinBoot = (data) => {
  try {
    const q = data.query || initialQuery || "";
    if (input && q) input.value = q;
    setStatus("");
    renderList(data.ordinances || [], q);
  } catch (err) {
    console.error(err);
  }
};
