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

/** 띄어쓰기 없는 한글 4글자 복합어(예: 영업손실, 수용재결) → { full, left, right } */
export function detectHangulCompound(query) {
  const q = String(query || "").trim();
  if (!/^[가-힣]{4}$/.test(q)) return null;
  return { full: q, left: q.slice(0, 2), right: q.slice(2) };
}

/** 공백·구분자로 나뉜 2어휘 이상 검색어 → { full, terms } */
export function detectMultiWordQuery(query) {
  const q = String(query || "").trim();
  if (!q) return null;
  const terms = q.split(/[\s,/·ㆍ]+/).filter((t) => t.length >= 2);
  if (terms.length < 2) return null;
  return { full: q, terms };
}

/**
 * AND/OR(·exact) 선택이 필요한 검색어인지 판별.
 * 복합어(4글자 한글) 우선, 그다음 다어휘.
 * @returns {{ type: "compound"|"multi", full: string, terms: string[], left?: string, right?: string } | null}
 */
export function detectMatchChoice(query) {
  const compound = detectHangulCompound(query);
  if (compound) {
    return {
      type: "compound",
      full: compound.full,
      left: compound.left,
      right: compound.right,
      terms: [compound.left, compound.right],
    };
  }
  const multi = detectMultiWordQuery(query);
  if (multi) {
    return { type: "multi", full: multi.full, terms: multi.terms };
  }
  return null;
}

export function normalizeMatchMode(mode) {
  const value = String(mode || "").trim().toLowerCase();
  if (!value) return "";
  if (value === "exact" || value === "phrase" || value === "only") return "exact";
  if (value === "or" || value === "any") return "or";
  if (value === "and" || value === "all") return "and";
  return "";
}

/** 복합어·다어휘 검색 방식 선택 카드 HTML */
export function matchModePromptHtml(choice, { askText = "어떻게 검색할까요?" } = {}) {
  if (!choice?.full || !Array.isArray(choice.terms) || choice.terms.length < 2) return "";
  const terms = choice.terms;
  const listed = terms.map((t) => `「${escapeHtml(t)}」`).join(", ");
  const andLabel = terms.map(escapeHtml).join(" AND ");
  const orLabel = terms.map(escapeHtml).join(" OR ");
  const isCompound = choice.type === "compound";
  const title = isCompound
    ? `「${escapeHtml(choice.full)}」은 ${listed}로 나눌 수 있는 검색어로 보입니다.`
    : `「${escapeHtml(choice.full)}」은 ${listed}로 이뤄진 검색어입니다.`;
  const kicker = isCompound ? "복합 검색어" : "다어휘 검색어";
  const exactBtn = isCompound
    ? `<button type="button" class="prompt-primary" data-match-mode="exact">
          ${escapeHtml(choice.full)}만
        </button>`
    : "";
  const andClass = isCompound ? "prompt-secondary" : "prompt-primary";
  return `
    <div class="compound-prompt-card">
      <div>
        <p class="compound-prompt-kicker">${kicker}</p>
        <h2>${title}</h2>
        <p class="compound-prompt-ask">${escapeHtml(askText)}</p>
      </div>
      <div class="compound-prompt-actions">
        ${exactBtn}
        <button type="button" class="${andClass}" data-match-mode="and">
          ${andLabel}
        </button>
        <button type="button" class="prompt-secondary" data-match-mode="or">
          ${orLabel}
        </button>
      </div>
    </div>
  `;
}

export function queryTerms(query, matchMode = "") {
  const q = (query || "").trim();
  if (!q) return [];
  const mode = normalizeMatchMode(matchMode);

  // exact(원문만): 분절하지 않고 입력 구절 그대로만 강조
  if (mode === "exact") {
    return q.length >= 2 ? [q] : [];
  }

  const parts = q.split(/[\s,/·ㆍ]+/).filter((t) => t.length >= 2);
  const terms = [];
  const seen = new Set();

  const add = (term) => {
    if (!term || term.length < 2 || seen.has(term)) return;
    seen.add(term);
    terms.push(term);
  };

  for (const term of [q, ...parts]) {
    add(term);
    // and/or·기본: 띄어쓰기 없는 한글 복합어(예: 수용재결)도 분절해 강조
    if (/^[가-힣]{4,10}$/.test(term)) {
      if (term.length === 4) {
        add(term.slice(0, 2));
        add(term.slice(2));
      } else {
        for (const cut of [2, 3]) {
          if (term.length - cut >= 2) {
            add(term.slice(0, cut));
            add(term.slice(cut));
          }
        }
      }
    }
  }
  // 긴 키워드부터 치환해 부분 중복 하이라이트 깨짐을 줄임
  terms.sort((a, b) => b.length - a.length);
  return terms;
}

export function highlightText(text, query, matchMode = "") {
  const source = String(text ?? "");
  const terms = queryTerms(query, matchMode);
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

/** 결과 화면용 강조 안내 문구 (선택 matchMode와 맞춤) */
export function highlightHintHtml(query, matchMode = "") {
  const q = String(query || "").trim();
  if (!q) return "";
  const mode = normalizeMatchMode(matchMode);
  const choice = detectMatchChoice(q);
  const qMark = `<mark class="hit inline-hit">${escapeHtml(q)}</mark>`;

  if (mode === "exact" || !choice || !mode) {
    return `노란 강조는 검색어 ${qMark} 와 일치하는 부분입니다.`;
  }

  const termMarks = choice.terms
    .map((t) => `<mark class="hit inline-hit">${escapeHtml(t)}</mark>`)
    .join(", ");
  if (mode === "or") {
    return `노란 강조는 검색어 ${qMark} 또는 나뉜 단어(${termMarks})와 일치하는 부분입니다.`;
  }
  // and
  return `노란 강조는 검색어 ${qMark} 및 나뉜 단어(${termMarks})와 일치하는 부분입니다.`;
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
