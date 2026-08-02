const params = new URLSearchParams(location.search);
const lawId = (params.get("lawId") || "").trim();
const lawName = (params.get("lawName") || "").trim();
const initialQuery = (params.get("q") || "").trim();
const modeParam = (params.get("mode") || "").trim().toLowerCase();
const mode = modeParam === "full" ? "full" : "scoped";

const form = document.getElementById("search-form");
const input = document.getElementById("query");
const button = document.getElementById("search-btn");
const searchBar = document.getElementById("search-bar");
const openAllBtn = document.getElementById("open-all-btn");
const statusEl = document.getElementById("status");
const metaEl = document.getElementById("meta");
const compareEl = document.getElementById("compare");
const chipsEl = document.getElementById("chips");
const pageTitle = document.getElementById("page-title");
const scopePill = document.getElementById("scope-pill");
const scopeLead = document.getElementById("scope-lead");
const workspaceEl = document.getElementById("workspace");

const COLUMN_ORDER = ["법률", "시행령", "시행규칙"];

let currentQuery = "";

function openFullArticlesWindow() {
  if (!lawId) {
    setStatus("법률을 먼저 선택한 뒤 전체 조문을 열어 주세요.", true);
    return;
  }
  const next = new URLSearchParams({
    mode: "full",
    lawId,
    lawName: lawName || "",
  });
  const url = `/law?${next.toString()}`;
  const features = "noopener,noreferrer,width=1400,height=900";
  const win = window.open(url, `law-full-${lawId}`, features);
  if (win) win.opener = null;
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
  // 전체 문장을 먼저, 그다음 개별 토큰
  for (const term of [q, ...parts]) {
    if (!term || seen.has(term)) continue;
    seen.add(term);
    terms.push(term);
  }
  // 긴 키워드부터 치환해 부분 중복 하이라이트 깨짐을 줄임
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

  try {
    const re = new RegExp(`(${pattern})`, "gi");
    return escaped.replace(re, `<mark class="hit">$1</mark>`);
  } catch {
    return escaped;
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

function currencyBadge(currency) {
  if (!currency) {
    return `<span class="currency-badge is-unknown">현행 여부 미확인</span>`;
  }
  const code = currency.code || "unknown";
  const label = escapeHtml(currency.label || "현행 여부 미확인");
  return `<span class="currency-badge is-${escapeHtml(code)}">${label}</span>`;
}

function currencyMeta(currency) {
  if (!currency) return "";
  const upcoming = Array.isArray(currency.upcoming) ? currency.upcoming : [];
  const current = currency.current;
  const bits = [];
  if (currency.detail) {
    bits.push(`<p class="currency-detail">${escapeHtml(currency.detail)}</p>`);
  }
  if (current?.effectiveDate) {
    bits.push(
      `<p class="currency-ref">현행 기준 시행일 <strong>${escapeHtml(
        current.effectiveDate
      )}</strong>${
        current.promulgationDate
          ? ` · 공포 ${escapeHtml(current.promulgationDate)}`
          : ""
      }</p>`
    );
  }
  if (upcoming.length) {
    bits.push(
      `<p class="currency-upcoming">시행 예정 ${upcoming.length}건` +
        upcoming
          .slice(0, 2)
          .map(
            (u) =>
              ` · ${escapeHtml(u.effectiveDate)}${
                u.revisionType ? `(${escapeHtml(u.revisionType)})` : ""
              }`
          )
          .join("") +
        `</p>`
    );
  }
  return bits.join("");
}

function instrumentBlock(cat, instrument) {
  if (!instrument) {
    return `
      <div class="scope-item" data-cat="${escapeHtml(cat)}">
        <span class="badge ${escapeHtml(cat)}">${escapeHtml(cat)}</span>
        <div class="scope-item-body">
          <strong>없음</strong>
        </div>
      </div>`;
  }

  const currency = instrument.currency;

  return `
    <div class="scope-item" data-cat="${escapeHtml(cat)}">
      <div class="scope-item-top">
        <span class="badge ${escapeHtml(cat)}">${escapeHtml(cat)}</span>
        ${currencyBadge(currency)}
      </div>
      <div class="scope-item-body">
        <strong>${escapeHtml(instrument.lawName)}</strong>
        <span class="scope-date">
          ${
            instrument.effectiveDate
              ? `시행 ${escapeHtml(instrument.effectiveDate)}`
              : "시행일 정보 없음"
          }
          ${
            instrument.promulgationDate
              ? ` · 공포 ${escapeHtml(instrument.promulgationDate)}`
              : ""
          }
        </span>
        ${currencyMeta(currency)}
      </div>
    </div>`;
}

function encodeLawUrl(url) {
  const value = String(url || "");
  if (!value) return "";
  if (value.startsWith("data:") || value.startsWith("blob:")) return value;
  try {
    // 한글 경로가 포함된 법령 URL을 안전하게 인코딩
    return encodeURI(decodeURI(value));
  } catch {
    return value;
  }
}

function openExternalWindow(url) {
  let href = encodeLawUrl(url);
  if (!href) return;
  // 상대 경로 이미지는 절대 URL로 변환
  if (href.startsWith("/")) {
    href = `${location.origin}${href}`;
  }
  const features =
    "noopener,noreferrer,width=1280,height=900,menubar=yes,toolbar=yes,scrollbars=yes,resizable=yes";
  const win = window.open(href, "_blank", features);
  if (win) {
    win.opener = null;
  } else {
    // 팝업 차단 시 새 탭으로라도 연다
    const a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
}

function renderContentBlocks(blocks, query, fallbackText) {
  const list = Array.isArray(blocks) ? blocks : [];
  if (!list.length) {
    return `<div class="article-body">${highlightText(fallbackText || "", query)}</div>`;
  }

  return `<div class="article-body rich-body">${list
    .map((block) => {
      if (block?.type === "image") {
        const src = escapeHtml(block.src || "");
        const alt = escapeHtml(block.alt || "조문 이미지");
        if (!src) return "";
        return `
          <figure class="law-figure">
            <a
              href="${src}"
              class="law-figure-link"
              data-open-image
              target="_blank"
              rel="noopener noreferrer"
              title="새 창에서 이미지 보기"
            >
              <img src="${src}" alt="${alt}" loading="lazy" decoding="async" />
            </a>
          </figure>`;
      }
      return `<div class="article-text">${highlightText(block?.text || "", query)}</div>`;
    })
    .join("")}</div>`;
}

function articleCard(article, query) {
  const titleRaw = article.articleTitle
    ? `${article.articleLabel}(${article.articleTitle})`
    : article.articleLabel;
  const detailUrl = encodeLawUrl(article.detailUrl);

  return `
    <article class="tri-article is-compact" data-law-id="${escapeHtml(article.lawId)}" data-jo="${escapeHtml(
      article.joParam
    )}">
      <div class="tri-article-head">
        <span class="article-label">${highlightText(titleRaw, query)}</span>
      </div>
      ${renderContentBlocks(article.contentBlocks, query, article.articleContent)}
      <div class="article-meta">
        ${article.effectiveDate ? `<span>조문 시행 ${escapeHtml(article.effectiveDate)}</span>` : ""}
        <a
          href="${escapeHtml(detailUrl)}"
          class="source-open"
          data-open-source
          target="_blank"
          rel="noopener noreferrer"
        >원문</a>
        <button type="button" class="refresh" data-refresh>최신</button>
      </div>
    </article>
  `;
}

function renderCompare(data) {
  const baseName = data.baseLaw?.lawName || lawName || "선택한 법률";
  const isFull = data.mode === "full";
  const query = isFull ? "" : data.query || currentQuery;
  currentQuery = query;

  pageTitle.textContent = isFull ? `${baseName} · 전체 조문` : baseName;
  document.title = isFull ? `${baseName} · 전체 조문` : `${baseName} · 3단 검색`;

  workspaceEl.hidden = false;
  scopePill.hidden = false;
  scopePill.innerHTML = COLUMN_ORDER.map((cat) =>
    instrumentBlock(cat, data.instruments?.[cat])
  ).join("");

  metaEl.hidden = false;
  metaEl.innerHTML = `
    <div class="query-banner">
      <span class="query-banner-label">${isFull ? "보기" : "검색어"}</span>
      <strong class="query-banner-text">${escapeHtml(isFull ? "전체 조문" : query)}</strong>
    </div>
    <span class="pill">${isFull ? "전체 조문" : "관련 조문"} ${data.total || 0}건</span>
    ${COLUMN_ORDER.map((cat) => {
      const n = data.columns?.[cat]?.length || 0;
      return `<span class="pill">${escapeHtml(cat)} ${n}</span>`;
    }).join("")}
  `;

  const scopeLabel = isFull ? "선택 법령 · 전체 조문 3단 비교" : "선택 법령 범위 · 3단 비교";
  const scopeTitle = isFull
    ? `「${escapeHtml(baseName)}」 전체 조문`
    : `「${escapeHtml(baseName)}」 관련 조문`;
  const scopeDescription = isFull
    ? "선택한 법률과 대응 시행령·시행규칙의 전체 조문을 키워드 필터 없이 표시합니다."
    : `노란색 표시는 검색어 <mark class="hit inline-hit">${escapeHtml(query)}</mark> 와 일치하는 부분입니다.`;

  compareEl.innerHTML = `
    <div class="compare-toolbar">
      <div>
        <p class="compare-kicker">${scopeLabel}</p>
        <h2>${scopeTitle}</h2>
        <p class="compare-sub">
          ${scopeDescription}
        </p>
      </div>
    </div>
    <div class="tri-board">
      ${COLUMN_ORDER.map((cat) => {
        const instrument = data.instruments?.[cat];
        const articles = data.columns?.[cat] || [];
        return `
          <section class="tri-col" data-cat="${escapeHtml(cat)}">
            <header class="tri-col-head">
              <div>
                <p class="tri-cat">${escapeHtml(cat)}</p>
                <h3>${instrument ? escapeHtml(instrument.lawName) : "해당 없음"}</h3>
                <p class="tri-date">
                  ${
                    instrument?.effectiveDate
                      ? `시행 ${escapeHtml(instrument.effectiveDate)}`
                      : instrument
                        ? "시행일 정보 없음"
                        : ""
                  }
                </p>
                ${instrument ? currencyBadge(instrument.currency) : ""}
                ${instrument ? `<div class="tri-currency">${currencyMeta(instrument.currency)}</div>` : ""}
              </div>
              <span class="count">${articles.length}개</span>
            </header>
            <div class="tri-col-body">
              ${
                articles.length
                  ? articles.map((a) => articleCard(a, query)).join("")
                  : `<div class="col-empty">${
                      instrument
                        ? isFull
                          ? "조문이 없습니다."
                          : "관련 조문이 없습니다."
                        : `${cat}을(를) 찾지 못했습니다.`
                    }</div>`
              }
            </div>
          </section>`;
      }).join("")}
    </div>
  `;
}

async function refreshArticle(articleEl) {
  const id = articleEl.dataset.lawId;
  const jo = articleEl.dataset.jo;
  const body = articleEl.querySelector(".article-body");
  const btn = articleEl.querySelector("[data-refresh]");
  if (!id || !jo || !body || !btn) return;

  btn.disabled = true;
  btn.textContent = "…";
  try {
    const res = await fetch(
      `/api/article?lawId=${encodeURIComponent(id)}&jo=${encodeURIComponent(jo)}`
    );
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const rendered = renderContentBlocks(data.contentBlocks, currentQuery, data.articleContent);
    body.outerHTML = rendered;
    btn.textContent = "반영";
  } catch (err) {
    btn.textContent = "실패";
    console.error(err);
  } finally {
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = "최신";
    }, 1400);
  }
}

async function runScopedSearch(query) {
  const q = query.trim();
  if (!q || !lawId) return;

  currentQuery = q;
  button.disabled = true;
  button.textContent = "검색 중…";
  setStatus(`「${lawName || "선택 법률"}」 범위에서 조문을 찾는 중입니다…`);
  workspaceEl.hidden = false;
  metaEl.hidden = true;
  compareEl.innerHTML = `<div class="empty">조문을 불러오는 중…</div>`;

  const next = new URL(location.href);
  next.searchParams.set("q", q);
  next.searchParams.delete("mode");
  history.replaceState(null, "", next);

  try {
    const searchParams = new URLSearchParams({
      q,
      lawId,
      lawName: lawName || "",
      maxArticles: "50",
    });
    const res = await fetch(`/api/compare?${searchParams}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "조문 검색에 실패했습니다.");
    setStatus("");
    renderCompare(data);
  } catch (err) {
    setStatus(err.message || "검색 중 오류가 발생했습니다.", true);
    compareEl.innerHTML = `<div class="empty error-box">조문을 불러오지 못했습니다.</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "조문 검색";
  }
}

async function runFullArticles() {
  if (!lawId) return;

  currentQuery = "";
  if (openAllBtn) {
    openAllBtn.disabled = true;
    openAllBtn.textContent = "불러오는 중…";
  }
  setStatus(`「${lawName || "선택 법률"}」 전체 조문을 불러오는 중입니다…`);
  workspaceEl.hidden = false;
  metaEl.hidden = true;
  compareEl.innerHTML = `<div class="empty">전체 조문을 불러오는 중…</div>`;

  try {
    const searchParams = new URLSearchParams({
      lawId,
      lawName: lawName || "",
      maxArticles: "3000",
    });
    const res = await fetch(`/api/compare-full?${searchParams}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "전체 조문 조회에 실패했습니다.");
    setStatus("");
    renderCompare(data);
  } catch (err) {
    setStatus(err.message || "전체 조문 조회 중 오류가 발생했습니다.", true);
    compareEl.innerHTML = `<div class="empty error-box">전체 조문을 불러오지 못했습니다.</div>`;
  } finally {
    if (openAllBtn) {
      openAllBtn.disabled = true;
      openAllBtn.textContent = "전체 조문 표시 중";
    }
  }
}

function setupPage() {
  if (searchBar) {
    searchBar.classList.add("with-secondary");
  }

  if (!lawId) {
    pageTitle.textContent = "법률을 선택해 주세요";
    setStatus("법률 ID가 없습니다. 목록에서 법률을 다시 선택해 주세요.", true);
    form.querySelectorAll("input, button").forEach((el) => {
      el.disabled = true;
    });
    workspaceEl.hidden = true;
    return;
  }

  pageTitle.textContent = lawName || "법령 3단 검색";
  document.title = mode === "full"
    ? `${lawName || "법령"} · 전체 조문`
    : `${lawName || "법령"} · 3단 검색`;

  if (mode === "full") {
    scopeLead.innerHTML = `
      <em>${escapeHtml(lawName || "선택한 법률")}</em>과 그
      <em>시행령 · 시행규칙</em>의 <em>전체 조문</em>을 3단으로 보여 줍니다.
    `;
    if (openAllBtn) {
      openAllBtn.disabled = true;
      openAllBtn.textContent = "전체 조문 표시 중";
    }
  } else {
    scopeLead.innerHTML = `
      <em>${escapeHtml(lawName || "선택한 법률")}</em>과 그
      <em>시행령 · 시행규칙</em> 안에서만 키워드나 문장으로 조문을 검색합니다.
      <em>전체 조문</em>을 누르면 키워드와 무관하게 전체 조문을 새 창에서 볼 수 있습니다.
    `;
  }

  const suggestions = [];
  if (initialQuery) suggestions.push(initialQuery);
  if (lawName) {
    const short = lawName.replace(/\s*법$/, "").trim();
    if (short && short !== initialQuery) suggestions.push(short);
  }
  ["정의", "의무", "벌칙"].forEach((word) => {
    if (!suggestions.includes(word)) suggestions.push(word);
  });

  chipsEl.innerHTML = suggestions
    .slice(0, 5)
    .map((q) => `<button type="button" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
    .join("");

  if (mode === "full") {
    runFullArticles();
  } else if (initialQuery) {
    input.value = initialQuery;
    runScopedSearch(initialQuery);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runScopedSearch(input.value);
});

chipsEl.addEventListener("click", (event) => {
  const target = event.target.closest("button[data-q]");
  if (!target) return;
  input.value = target.dataset.q;
  runScopedSearch(target.dataset.q);
});

compareEl.addEventListener("click", (event) => {
  const imageLink = event.target.closest("[data-open-image]");
  if (imageLink) {
    event.preventDefault();
    openExternalWindow(imageLink.getAttribute("href"));
    return;
  }

  const sourceLink = event.target.closest("[data-open-source]");
  if (sourceLink) {
    event.preventDefault();
    openExternalWindow(sourceLink.getAttribute("href"));
    return;
  }

  const btn = event.target.closest("[data-refresh]");
  if (!btn) return;
  const articleEl = btn.closest(".tri-article");
  if (articleEl) refreshArticle(articleEl);
});

setupPage();

if (openAllBtn) {
  openAllBtn.addEventListener("click", () => {
    openFullArticlesWindow();
  });
}
