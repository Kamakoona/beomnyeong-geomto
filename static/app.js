import { escapeHtml, setStatus as setStatusEl } from "./shared.js";

const form = document.getElementById("search-form");
const input = document.getElementById("query");
const button = document.getElementById("search-btn");
const stopBtn = document.getElementById("stop-btn");
const searchBar = form?.querySelector(".search-bar");
const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const lawListEl = document.getElementById("law-list");
const chips = document.getElementById("chips");

let latestOrdinances = [];
let searchAbort = null;

function setSearching(isSearching) {
  button.disabled = isSearching;
  button.textContent = isSearching ? "검색 중…" : "법률 찾기";
  if (stopBtn) {
    stopBtn.hidden = !isSearching;
    stopBtn.disabled = !isSearching;
  }
  searchBar?.classList.toggle("with-secondary", isSearching);
}

function abortSearch() {
  if (!searchAbort) return;
  searchAbort.abort();
}

function setStatus(message, isError = false) {
  setStatusEl(statusEl, message, isError);
}

function openInNewTab(url) {
  const href = String(url || "").trim();
  if (!href) return false;
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  a.remove();
  return true;
}

function openOrdinanceTab(query) {
  const q = String(query || "").trim();
  if (!q) return;
  openInNewTab(`/ordin?q=${encodeURIComponent(q)}`);
}

function hideOrdinancePrompt() {
  const el = document.getElementById("ordinance-prompt");
  if (el) el.remove();
}

function ordinanceSamples(ordinances) {
  return ordinances
    .slice(0, 3)
    .map((item) => item.ordinName || "")
    .filter(Boolean)
    .join(", ");
}

function bindOrdinancePromptActions(root, query) {
  root.querySelector("[data-ordin-open]")?.addEventListener("click", () => {
    openOrdinanceTab(query);
    hideOrdinancePrompt();
  });
  root.querySelector("[data-ordin-dismiss]")?.addEventListener("click", () => {
    hideOrdinancePrompt();
  });
}

function ordinancePromptHtml(query, ordinances) {
  const count = ordinances.length;
  const samples = ordinanceSamples(ordinances);
  return `
    <div class="ordinance-prompt-card">
      <div>
        <p class="ordinance-prompt-kicker">자치법규 검색 결과</p>
        <h2>자치법규 ${count}건에서 「${escapeHtml(query)}」가 확인되었습니다.</h2>
        <p class="ordinance-prompt-sub">
          법률·시행령·시행규칙에는 없거나 부족해도, 조례 등 자치법규에는 있을 수 있습니다.
          ${samples ? `예: ${escapeHtml(samples)}${count > 3 ? " 외" : ""}` : ""}
        </p>
        <p class="ordinance-prompt-ask">자치법규 결과를 새 탭에서 열어볼까요?</p>
      </div>
      <div class="ordinance-prompt-actions">
        <button type="button" class="prompt-primary" data-ordin-open>새 탭에서 열기</button>
        <button type="button" class="prompt-secondary" data-ordin-dismiss>닫기</button>
      </div>
    </div>
  `;
}

function showOrdinancePrompt(query, ordinances) {
  hideOrdinancePrompt();
  if (!ordinances.length) return;

  const prompt = document.createElement("section");
  prompt.id = "ordinance-prompt";
  prompt.className = "ordinance-prompt";
  prompt.innerHTML = ordinancePromptHtml(query, ordinances);
  lawListEl.insertAdjacentElement("beforebegin", prompt);
  bindOrdinancePromptActions(prompt, query);
}

function openLawWindow(lawId, lawName, query) {
  const params = new URLSearchParams({
    lawId,
    lawName: lawName || "",
  });
  if (query) params.set("q", query);
  const url = `/law?${params.toString()}`;
  const win = window.open(url, "_blank");
  if (win) {
    win.opener = null;
    return;
  }
  setStatus("팝업이 차단되었습니다. 브라우저에서 팝업을 허용하거나 링크를 새 탭으로 열어 주세요.", true);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  anchor.textContent = `「${lawName}」 새 탭에서 열기`;
  anchor.className = "fallback-link";
  statusEl.appendChild(document.createElement("br"));
  statusEl.appendChild(anchor);
}

const INITIAL_LAW_LIMIT = 20;

function lawCardHtml(law) {
  return `
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
        ${law.hitCount ? `<span>관련조문 ${law.hitCount}</span>` : ""}
      </span>
      <span class="law-card-action">새 탭에서 검색 →</span>
    </button>`;
}

function renderSearchMeta(query, laws) {
  const statuteCount = laws.filter((l) => l.category === "법률").length;
  const ordinCount = latestOrdinances.length;
  metaEl.hidden = false;
  metaEl.innerHTML = `
    <span>검색어 <strong>${escapeHtml(query)}</strong></span>
    <span class="pill">관련 법령 ${laws.length}건</span>
    ${statuteCount ? `<span class="pill">법률 ${statuteCount}건</span>` : ""}
    ${ordinCount ? `<span class="pill">자치법규 ${ordinCount}건</span>` : ""}
    <span class="hint">${
      laws.length
        ? "법률·시행령·시행규칙 중 하나를 선택하면 새 탭에서 3단으로 검색합니다"
        : ordinCount
          ? "관련 법률은 없지만 자치법규(조례 등)에서 검색되었습니다"
          : "다른 키워드로 다시 검색해 보세요"
    }</span>
  `;
}

function renderLawList(laws, query, { expanded = false } = {}) {
  if (!laws.length) {
    renderSearchMeta(query, laws);
    if (latestOrdinances.length) {
      lawListEl.innerHTML = `
        <div class="empty empty-with-ordinance">
          <p>관련 법률·시행령·시행규칙은 찾지 못했습니다.</p>
          <p class="empty-ordinance-note">다만 자치법규 ${latestOrdinances.length}건에서 「${escapeHtml(
            query
          )}」가 확인되었습니다. 아래에서 새 탭으로 열어볼 수 있습니다.</p>
        </div>`;
      return;
    }
    lawListEl.innerHTML = `<div class="empty">관련 법률을 찾지 못했습니다. 다른 키워드로 검색해 보세요.</div>`;
    return;
  }

  const hasMore = laws.length > INITIAL_LAW_LIMIT;
  const visible = expanded || !hasMore ? laws : laws.slice(0, INITIAL_LAW_LIMIT);
  const remaining = laws.length - INITIAL_LAW_LIMIT;

  renderSearchMeta(query, laws);

  lawListEl.innerHTML = `
    <div class="law-list-head">
      <h2>관련 법령 선택</h2>
      <p class="law-list-sub">시행령·시행규칙을 골라도 대응 법률·시행령·시행규칙이 함께 3단으로 열립니다.</p>
    </div>
    <div class="law-grid">
      ${visible.map(lawCardHtml).join("")}
    </div>
    ${
      hasMore && !expanded
        ? `<div class="law-list-more">
            <button type="button" class="more-btn" data-show-more>
              더 보기 <span class="more-count">(+${remaining})</span>
            </button>
          </div>`
        : ""
    }
  `;

  lawListEl._laws = laws;
  lawListEl._query = query;
}

async function runSearch(query) {
  const q = query.trim();
  if (!q) return;

  if (searchAbort) searchAbort.abort();
  const controller = new AbortController();
  searchAbort = controller;

  setSearching(true);
  setStatus("관련 법률을 찾는 중입니다…");
  metaEl.hidden = true;
  metaEl.innerHTML = "";
  lawListEl.innerHTML = "";
  lawListEl._laws = [];
  lawListEl._query = q;
  latestOrdinances = [];
  hideOrdinancePrompt();

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&display=80`, {
      signal: controller.signal,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "검색에 실패했습니다.");
    if (controller.signal.aborted) return;
    setStatus("");
    const laws = Array.isArray(data.laws) ? data.laws : [];
    latestOrdinances = Array.isArray(data.ordinances) ? data.ordinances : [];
    renderLawList(laws, data.query || q, { expanded: false });
    if (latestOrdinances.length) {
      showOrdinancePrompt(data.query || q, latestOrdinances);
    }
  } catch (err) {
    if (err?.name === "AbortError") {
      if (searchAbort === controller) {
        setStatus("검색을 중단했습니다.");
        lawListEl.innerHTML = "";
        lawListEl._laws = [];
      }
      return;
    }
    setStatus(err.message || "검색 중 오류가 발생했습니다.", true);
    lawListEl.innerHTML = "";
    lawListEl._laws = [];
  } finally {
    if (searchAbort === controller) {
      searchAbort = null;
      setSearching(false);
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch(input.value);
});

stopBtn?.addEventListener("click", () => {
  abortSearch();
});

chips.addEventListener("click", (event) => {
  const target = event.target.closest("button[data-q]");
  if (!target) return;
  input.value = target.dataset.q;
  runSearch(target.dataset.q);
});

lawListEl.addEventListener("click", (event) => {
  const moreBtn = event.target.closest("[data-show-more]");
  if (moreBtn) {
    renderLawList(lawListEl._laws || [], lawListEl._query || input.value.trim(), {
      expanded: true,
    });
    return;
  }

  const card = event.target.closest("[data-open-law]");
  if (!card) return;
  openLawWindow(card.dataset.lawId, card.dataset.lawName, input.value.trim());
});

const params = new URLSearchParams(location.search);
if (params.get("q")) {
  input.value = params.get("q");
  runSearch(params.get("q"));
}
