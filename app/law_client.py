from __future__ import annotations

import asyncio
import os
import re
from datetime import date, datetime
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

LAW_BASE = "https://www.law.go.kr/DRF"
DEFAULT_OC = os.getenv("LAW_API_OC", "test")

LAW_TYPES = {"법률", "헌법"}
DECREE_TYPES = {"대통령령"}

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.law.go.kr/",
}


def get_oc() -> str:
    return os.getenv("LAW_API_OC", DEFAULT_OC)


def classify_law_kind(kind_name: str, law_name: str = "") -> str:
    """법률 / 시행령 / 시행규칙 으로 분류."""
    kind = (kind_name or "").strip()
    name = (law_name or "").strip()

    if "시행령" in name or kind == "대통령령":
        return "시행령"
    if "시행규칙" in name or name.endswith("규칙") or "규칙" in kind:
        return "시행규칙"
    if kind in LAW_TYPES or (name.endswith("법") and "령" not in name):
        return "법률"
    if kind in DECREE_TYPES:
        return "시행령"
    if kind.endswith("부령") or kind.endswith("청령") or kind == "총리령":
        return "시행규칙"
    if name.endswith("령"):
        return "시행령"
    return "기타"


def article_sort_key(article_no: str | int | None, branch_no: str | int | None = None) -> tuple[int, int]:
    def to_int(value: str | int | None) -> int:
        if value is None:
            return 0
        text = str(value).strip()
        digits = re.sub(r"\D", "", text)
        return int(digits) if digits else 0

    return (to_int(article_no), to_int(branch_no))


def format_article_label(article_no: str | int | None, branch_no: str | int | None = None) -> str:
    main = str(int(re.sub(r"\D", "", str(article_no or "0")) or 0))
    branch_digits = re.sub(r"\D", "", str(branch_no or "0"))
    branch = int(branch_digits) if branch_digits else 0
    if branch:
        return f"제{main}조의{branch}"
    return f"제{main}조"


def format_date(value: str | int | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\D", "", str(value))
    if len(text) >= 8:
        return f"{text[:4]}.{text[4:6]}.{text[6:8]}"
    return str(value)


def jo_param(article_no: str | int | None, branch_no: str | int | None = None) -> str:
    return (
        f"{int(re.sub(r'\D', '', str(article_no)) or 0):04d}"
        f"{int(re.sub(r'\D', '', str(branch_no)) or 0):02d}"
    )


def query_tokens(query: str) -> list[str]:
    raw = re.split(r"[\s,/·ㆍ]+", query.strip())
    tokens = [t for t in raw if len(t) >= 2]
    # dedupe preserving order
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


def primary_keyword(query: str, tokens: list[str]) -> str:
    """검색어에서 법령명 조회용 핵심 키워드를 고른다."""
    if not tokens:
        return query.strip()
    # 띄어쓰기 없는 단일 토큰 중 가장 긴 것 우선
    return max(tokens, key=lambda t: (len(t), t == tokens[0]))


def text_matches(text: str, tokens: list[str], full_query: str = "") -> bool:
    if not text:
        return False
    if full_query and full_query in text:
        return True
    if not tokens:
        return True
    if len(tokens) == 1:
        return tokens[0] in text
    # 문장·복수 키워드: 모든 토큰이 조문에 포함
    return all(token in text for token in tokens)


def normalize_article(raw: dict[str, Any], *, fallback_category: str | None = None) -> dict[str, Any]:
    law_name = raw.get("법령명") or raw.get("법령명한글") or raw.get("lawName") or ""
    kind_name = raw.get("법령종류명") or raw.get("법령구분명") or raw.get("lawKind") or ""
    article_no = raw.get("조문번호") or raw.get("articleNo") or "0"
    branch_no = raw.get("조문가지번호") or raw.get("articleBranch") or "0"
    category = fallback_category or classify_law_kind(kind_name, law_name)
    law_id_padded = str(raw.get("법령ID") or raw.get("lawId") or "").zfill(6)

    content = (raw.get("조문내용") or raw.get("articleContent") or "").strip()
    title = raw.get("조문제목") or raw.get("articleTitle") or ""
    blocks = raw.get("contentBlocks")
    if not isinstance(blocks, list):
        blocks = [{"type": "text", "text": content}] if content else []

    return {
        "id": raw.get("id"),
        "lawId": law_id_padded,
        "mst": str(raw.get("법령일련번호") or raw.get("mst") or ""),
        "lawName": law_name,
        "lawKind": kind_name,
        "category": category,
        "ministry": raw.get("소관부처명") or raw.get("ministry") or "",
        "articleNo": str(article_no),
        "articleBranch": str(branch_no),
        "articleLabel": format_article_label(article_no, branch_no),
        "articleTitle": title,
        "articleContent": content,
        "contentBlocks": blocks,
        "effectiveDate": format_date(raw.get("시행일자") or raw.get("effectiveDate")),
        "promulgationDate": format_date(raw.get("공포일자") or raw.get("promulgationDate")),
        "promulgationNo": str(raw.get("공포번호") or ""),
        "revisionType": raw.get("제개정구분명") or "",
        "sortKey": article_sort_key(article_no, branch_no),
        "detailUrl": f"https://www.law.go.kr/법령/{law_name}" if law_name else "https://www.law.go.kr",
        "joParam": jo_param(article_no, branch_no),
    }


async def fetch_json(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
    query = {"OC": get_oc(), "type": "JSON", **params}
    response = await client.get(f"{LAW_BASE}/{path}", params=query, timeout=45.0)
    response.raise_for_status()
    return response.json()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


async def search_ai_articles(client: httpx.AsyncClient, query: str, display: int) -> list[dict[str, Any]]:
    data = await fetch_json(
        client,
        "lawSearch.do",
        {
            "target": "aiSearch",
            "search": 0,
            "query": query,
            "display": display,
            "page": 1,
        },
    )
    root = data.get("aiSearch") or {}
    items = as_list(root.get("법령조문"))
    return [normalize_article(item) for item in items if isinstance(item, dict)]


async def search_laws(
    client: httpx.AsyncClient,
    query: str,
    *,
    search: int,
    display: int = 20,
) -> list[dict[str, Any]]:
    data = await fetch_json(
        client,
        "lawSearch.do",
        {
            "target": "law",
            "query": query,
            "display": display,
            "page": 1,
            "search": search,
        },
    )
    root = data.get("LawSearch") or {}
    items = as_list(root.get("law"))
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("법령명한글") or ""
        kind = item.get("법령구분명") or ""
        results.append(
            {
                "lawId": str(item.get("법령ID") or "").zfill(6),
                "mst": str(item.get("법령일련번호") or ""),
                "lawName": name,
                "lawKind": kind,
                "category": classify_law_kind(kind, name),
                "ministry": item.get("소관부처명") or "",
                "effectiveDate": format_date(item.get("시행일자")),
                "promulgationDate": format_date(item.get("공포일자")),
                "revisionType": item.get("제개정구분명") or "",
                "historyCode": item.get("현행연혁코드") or "",
                "detailUrl": f"https://www.law.go.kr/법령/{name}",
            }
        )
    return results


def parse_ymd(value: str | int | None) -> date | None:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) < 8:
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def today_kst() -> date:
    # 서버 로컬 날짜 사용 (Windows KST 환경 가정)
    return datetime.now().date()


async def search_eflaw_by_lid(
    client: httpx.AsyncClient,
    law_id: str,
    *,
    nw: str,
    display: int = 10,
) -> list[dict[str, Any]]:
    """현행법령(시행일) 목록에서 법령ID 기준으로 현행/예정/연혁을 조회."""
    lid = str(law_id).lstrip("0") or "0"
    data = await fetch_json(
        client,
        "lawSearch.do",
        {
            "target": "eflaw",
            "query": "*",
            "LID": lid,
            "nw": nw,
            "display": display,
            "page": 1,
        },
    )
    root = data.get("LawSearch") or {}
    items = as_list(root.get("law"))
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "lawId": str(item.get("법령ID") or "").zfill(6),
                "mst": str(item.get("법령일련번호") or ""),
                "lawName": item.get("법령명한글") or "",
                "historyCode": item.get("현행연혁코드") or "",
                "effectiveDate": format_date(item.get("시행일자")),
                "effectiveDateRaw": re.sub(r"\D", "", str(item.get("시행일자") or "")),
                "promulgationDate": format_date(item.get("공포일자")),
                "revisionType": item.get("제개정구분명") or "",
            }
        )
    return results


async def assess_instrument_currency(
    client: httpx.AsyncClient,
    law: dict[str, Any],
) -> dict[str, Any]:
    """선택한 법령본문이 현행 최신인지·시행 중인지 판정."""
    law_id = str(law.get("lawId") or "").zfill(6)
    today = today_kst()
    loaded_ef = parse_ymd(law.get("effectiveDate"))
    loaded_mst = str(law.get("mst") or "")

    current_list: list[dict[str, Any]] = []
    scheduled_list: list[dict[str, Any]] = []
    try:
        current_list, scheduled_list = await asyncio.gather(
            search_eflaw_by_lid(client, law_id, nw="3", display=5),
            search_eflaw_by_lid(client, law_id, nw="2", display=10),
        )
    except Exception:  # noqa: BLE001
        current_list, scheduled_list = [], []

    current = current_list[0] if current_list else None
    current_ef = parse_ymd(current.get("effectiveDate")) if current else None
    current_mst = str(current.get("mst") or "") if current else ""

    upcoming = []
    for item in scheduled_list:
        ef = parse_ymd(item.get("effectiveDate"))
        if ef and ef > today:
            upcoming.append(
                {
                    "effectiveDate": item.get("effectiveDate") or "",
                    "promulgationDate": item.get("promulgationDate") or "",
                    "revisionType": item.get("revisionType") or "",
                    "mst": item.get("mst") or "",
                    "historyCode": item.get("historyCode") or "",
                }
            )
    upcoming.sort(key=lambda x: x.get("effectiveDate") or "")

    history_code = (current.get("historyCode") if current else "") or law.get("historyCode") or ""
    is_same_as_current = bool(current) and (
        (loaded_mst and current_mst and loaded_mst == current_mst)
        or (
            loaded_ef
            and current_ef
            and loaded_ef == current_ef
            and (not loaded_mst or not current_mst or loaded_mst == current_mst)
        )
        or (not loaded_mst and not loaded_ef and bool(current))
    )
    # eflaw ID 조회는 보통 현행본을 반환하므로, 목록 조회가 되면 현행으로 본다
    if current and not loaded_mst:
        is_same_as_current = True

    if current and current_ef and current_ef > today:
        code = "scheduled_current"
        label = "공포·현행 지정 · 시행 예정"
        detail = (
            f"현행으로 지정된 법령이나 시행일({current.get('effectiveDate')})이 아직 도래하지 않았습니다."
        )
        is_in_force = False
        is_latest = True
    elif current and is_same_as_current and (not current_ef or current_ef <= today):
        code = "current"
        label = "현행 시행 중"
        detail = "국가법령정보센터 기준 현행 법령이며, 현재 시행 중입니다."
        is_in_force = True
        is_latest = True
    elif current and not is_same_as_current:
        code = "outdated"
        label = "현행 아님(구법/불일치)"
        detail = (
            f"조회본과 현행본이 다릅니다. 현행 시행일 "
            f"{current.get('effectiveDate') or '미상'}."
        )
        is_in_force = bool(loaded_ef and loaded_ef <= today)
        is_latest = False
    elif history_code == "시행예정" or (loaded_ef and loaded_ef > today):
        code = "scheduled"
        label = "시행 예정"
        detail = f"시행일({law.get('effectiveDate') or '미상'}) 이후 적용되는 법령입니다."
        is_in_force = False
        is_latest = False
    elif history_code == "연혁":
        code = "history"
        label = "연혁 법령"
        detail = "과거 연혁 법령으로, 현행 최신본이 아닙니다."
        is_in_force = False
        is_latest = False
    else:
        code = "unknown"
        label = "현행 여부 확인 불가"
        detail = "현행/예정 정보를 확인하지 못했습니다."
        is_in_force = bool(loaded_ef and loaded_ef <= today)
        is_latest = False

    if upcoming and code == "current":
        detail += f" 앞으로 시행 예정인 개정이 {len(upcoming)}건 있습니다."

    return {
        "code": code,
        "label": label,
        "detail": detail,
        "isInForce": is_in_force,
        "isLatestCurrent": is_latest and is_in_force,
        "historyCode": history_code or (current.get("historyCode") if current else ""),
        "checkedAt": today.isoformat(),
        "current": {
            "mst": current_mst,
            "effectiveDate": current.get("effectiveDate") if current else "",
            "promulgationDate": current.get("promulgationDate") if current else "",
            "revisionType": current.get("revisionType") if current else "",
            "historyCode": current.get("historyCode") if current else "",
        }
        if current
        else None,
        "loaded": {
            "mst": loaded_mst,
            "effectiveDate": law.get("effectiveDate") or "",
            "promulgationDate": law.get("promulgationDate") or "",
        },
        "upcoming": upcoming[:5],
    }


async def fetch_related_laws(client: httpx.AsyncClient, law_name: str) -> dict[str, Any] | None:
    data = await fetch_json(
        client,
        "lawSearch.do",
        {
            "target": "lsRlt",
            "query": law_name,
        },
    )
    root = data.get("lsRltSearch") or {}
    law = root.get("법령")
    if not law:
        return None

    related = as_list(law.get("관련법령"))
    items = []
    for item in related:
        if not isinstance(item, dict):
            continue
        name = item.get("관련법령명") or ""
        relation = item.get("법령간관계") or ""
        category = classify_law_kind("", name)
        if "하위" in relation:
            if "시행령" in name:
                category = "시행령"
            elif "규칙" in name:
                category = "시행규칙"
        items.append(
            {
                "lawId": str(item.get("관련법령ID") or "").zfill(6),
                "lawName": name,
                "relation": relation,
                "category": category,
                "detailUrl": item.get("관련법령본문조회") or f"https://www.law.go.kr/법령/{name}",
            }
        )

    return {
        "baseLawId": str(law.get("기준법령ID") or "").zfill(6),
        "baseLawName": law.get("기준법령명") or "",
        "related": items,
    }


IMG_SRC_RE = re.compile(
    r"""<img\b[^>]*\bsrc\s*=\s*['"]([^'"]+)['"][^>]*>""",
    re.IGNORECASE,
)
FLSEQ_RE = re.compile(r"flSeq=(\d+)", re.IGNORECASE)
BOX_DRAWING_RE = re.compile(r"[┌┐└┘├┤┬┴┼─│┃┏┓┗┛━┃╔╗╚╝║═]|_{3,}|\|{2,}")


def extract_flseq(value: str) -> str | None:
    match = FLSEQ_RE.search(value or "")
    return match.group(1) if match else None


def looks_like_broken_graphic(text: str) -> bool:
    if not text:
        return False
    if BOX_DRAWING_RE.search(text):
        return True
    # 수식/표 ASCII 잔여물
    if text.count("─") >= 3 or text.count("━") >= 3:
        return True
    if re.search(r"_{5,}", text) and ("|" in text or "｜" in text):
        return True
    return False


def ascii_lines_to_svg_data_url(lines: list[str]) -> str:
    """깨진 ASCII 표·수식을 읽기 쉬운 SVG 이미지로 변환."""
    import base64
    import html as html_lib

    cleaned = [line.rstrip() for line in lines if line.strip()]
    if not cleaned:
        return ""
    font_size = 14
    line_height = 20
    padding = 16
    max_chars = max(len(line) for line in cleaned)
    width = max(320, padding * 2 + max_chars * 8)
    height = padding * 2 + line_height * len(cleaned)
    text_nodes = []
    y = padding + font_size
    for line in cleaned:
        text_nodes.append(
            f'<text x="{padding}" y="{y}" xml:space="preserve">'
            f"{html_lib.escape(line)}</text>"
        )
        y += line_height
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#fffdf6"/>'
        f'<g font-family="Consolas, Malgun Gothic, monospace" font-size="{font_size}" '
        f'fill="#12233a">'
        f'{"".join(text_nodes)}</g></svg>'
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def parse_content_nodes(value: Any) -> list[dict[str, Any]]:
    """항/호 내용(문자열·중첩 리스트)을 text/image 블록으로 변환."""
    blocks: list[dict[str, Any]] = []

    def emit_text(text: str) -> None:
        cleaned = text.strip("\n")
        if cleaned.strip():
            blocks.append({"type": "text", "text": cleaned})

    def emit_image(*, fl_seq: str | None = None, data_url: str | None = None, alt: str = "조문 이미지") -> None:
        if fl_seq:
            blocks.append(
                {
                    "type": "image",
                    "flSeq": fl_seq,
                    "src": f"/api/law-image?flSeq={fl_seq}",
                    "alt": alt,
                }
            )
        elif data_url:
            blocks.append({"type": "image", "src": data_url, "alt": alt, "flSeq": None})

    def handle_sequence(items: list[Any]) -> None:
        i = 0
        while i < len(items):
            item = items[i]
            if not isinstance(item, str):
                walk(item)
                i += 1
                continue

            raw = item.strip()
            img_match = IMG_SRC_RE.search(raw)
            if img_match or raw.lower().startswith("<img"):
                fl_seq = extract_flseq(raw)
                ascii_buffer: list[str] = []
                j = i + 1
                while j < len(items):
                    nxt = items[j]
                    if isinstance(nxt, str) and nxt.strip().lower() in {"</img>", "</ img>", "</IMG>"}:
                        j += 1
                        break
                    if isinstance(nxt, str):
                        # 이미지 대체 ASCII/표 텍스트는 버리고 공식 사용
                        if looks_like_broken_graphic(nxt) or fl_seq:
                            if not fl_seq and looks_like_broken_graphic(nxt):
                                ascii_buffer.append(nxt)
                            j += 1
                            continue
                        break
                    break

                if fl_seq:
                    emit_image(fl_seq=fl_seq, alt=f"img{fl_seq}")
                elif ascii_buffer:
                    data_url = ascii_lines_to_svg_data_url(ascii_buffer)
                    if data_url:
                        emit_image(data_url=data_url, alt="조문 표/수식")
                i = j
                continue

            if raw.lower() in {"</img>", "</ img>"}:
                i += 1
                continue

            if looks_like_broken_graphic(raw):
                ascii_buffer = [raw]
                j = i + 1
                while j < len(items) and isinstance(items[j], str) and looks_like_broken_graphic(items[j]):
                    ascii_buffer.append(items[j])
                    j += 1
                data_url = ascii_lines_to_svg_data_url(ascii_buffer)
                if data_url:
                    emit_image(data_url=data_url, alt="조문 표/수식")
                i = j
                continue

            emit_text(raw)
            i += 1

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            raw = node.strip()
            if not raw:
                return
            img_match = IMG_SRC_RE.search(raw)
            if img_match:
                # 문자열 한 덩어리에 텍스트+img가 섞인 경우
                parts = IMG_SRC_RE.split(raw)
                # split with capturing gives [text, src, text, src, text...]
                # Better iterate differently
                pos = 0
                for match in IMG_SRC_RE.finditer(raw):
                    before = raw[pos : match.start()]
                    if before.strip():
                        if looks_like_broken_graphic(before):
                            data_url = ascii_lines_to_svg_data_url(before.splitlines())
                            if data_url:
                                emit_image(data_url=data_url)
                        else:
                            emit_text(before)
                    fl_seq = extract_flseq(match.group(0))
                    if fl_seq:
                        emit_image(fl_seq=fl_seq, alt=f"img{fl_seq}")
                    pos = match.end()
                after = raw[pos:]
                after = re.sub(r"</img>", "", after, flags=re.IGNORECASE).strip()
                if after:
                    if looks_like_broken_graphic(after):
                        data_url = ascii_lines_to_svg_data_url(after.splitlines())
                        if data_url:
                            emit_image(data_url=data_url)
                    else:
                        emit_text(after)
                return
            if looks_like_broken_graphic(raw):
                data_url = ascii_lines_to_svg_data_url(raw.splitlines())
                if data_url:
                    emit_image(data_url=data_url)
                return
            emit_text(raw)
            return
        if isinstance(node, list):
            # 이미지 블록이 한 리스트에 묶여 오는 경우가 많음
            if node and all(isinstance(x, str) or isinstance(x, list) for x in node):
                flat_strings = []
                nested_lists = []
                for x in node:
                    if isinstance(x, list):
                        nested_lists.append(x)
                    else:
                        flat_strings.append(x)
                if flat_strings and any(
                    isinstance(s, str) and ("<img" in s.lower() or looks_like_broken_graphic(s))
                    for s in flat_strings
                ):
                    handle_sequence(flat_strings)
                    for nested in nested_lists:
                        walk(nested)
                    return
            for child in node:
                walk(child)
            return
        if isinstance(node, dict):
            for key in ("항내용", "호내용", "목내용", "조문내용", "content"):
                if key in node:
                    walk(node[key])
            return
        emit_text(str(node))

    walk(value)
    return blocks


def blocks_to_plain_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            parts.append(block.get("text") or "")
        elif block.get("type") == "image":
            parts.append("[이미지]")
    return "\n".join(p for p in parts if p).strip()


def flatten_article_unit(unit: dict[str, Any]) -> str:
    return blocks_to_plain_text(build_article_blocks(unit))


def build_article_blocks(unit: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    title = unit.get("조문내용")
    if title:
        blocks.extend(parse_content_nodes(title))

    hang = unit.get("항")
    if hang:
        for h in as_list(hang):
            if not isinstance(h, dict):
                continue
            if "항내용" in h:
                blocks.extend(parse_content_nodes(h.get("항내용")))
            for ho in as_list(h.get("호")):
                if not isinstance(ho, dict):
                    continue
                if "호내용" in ho:
                    blocks.extend(parse_content_nodes(ho.get("호내용")))
                for mok in as_list(ho.get("목")):
                    if isinstance(mok, dict) and "목내용" in mok:
                        blocks.extend(parse_content_nodes(mok.get("목내용")))
    elif not blocks and unit.get("조문내용"):
        pass

    # 인접 text 블록 병합
    merged: list[dict[str, Any]] = []
    for block in blocks:
        if (
            merged
            and block.get("type") == "text"
            and merged[-1].get("type") == "text"
        ):
            merged[-1]["text"] = f"{merged[-1]['text']}\n{block['text']}"
        else:
            merged.append(block)
    return merged


async def fetch_latest_article(law_id: str, jo: str) -> dict[str, Any] | None:
    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True) as client:
        data = await fetch_json(
            client,
            "lawService.do",
            {
                "target": "eflaw",
                "ID": law_id.zfill(6) if str(law_id).isdigit() else law_id,
                "JO": jo,
            },
        )

    root = data.get("법령") or {}
    basic = root.get("기본정보") or {}
    unit = (root.get("조문") or {}).get("조문단위")
    if not unit:
        return None
    unit = as_list(unit)[0]

    ministry = basic.get("소관부처")
    ministry_name = ministry.get("content") if isinstance(ministry, dict) else str(ministry or "")
    law_kind = basic.get("법종구분")
    kind_name = law_kind.get("content") if isinstance(law_kind, dict) else str(law_kind or "")
    law_name = basic.get("법령명_한글") or ""
    article_no = unit.get("조문번호")
    branch = unit.get("조문가지번호") or "0"

    return {
        "lawId": str(basic.get("법령ID") or law_id).zfill(6),
        "lawName": law_name,
        "lawKind": kind_name,
        "category": classify_law_kind(kind_name, law_name),
        "ministry": ministry_name,
        "articleNo": str(article_no),
        "articleBranch": str(branch),
        "articleLabel": format_article_label(article_no, branch),
        "articleTitle": unit.get("조문제목") or "",
        "articleContent": flatten_article_unit(unit),
        "contentBlocks": build_article_blocks(unit),
        "effectiveDate": format_date(unit.get("조문시행일자") or basic.get("시행일자")),
        "promulgationDate": format_date(basic.get("공포일자")),
        "detailUrl": f"https://www.law.go.kr/법령/{law_name}",
        "joParam": jo_param(article_no, branch),
    }


async def fetch_law_articles(
    client: httpx.AsyncClient,
    law: dict[str, Any],
    tokens: list[str],
    *,
    full_query: str = "",
    max_articles: int = 30,
    fallback_primary: bool = True,
) -> list[dict[str, Any]]:
    data = await fetch_json(
        client,
        "lawService.do",
        {
            "target": "eflaw",
            "ID": law["lawId"],
        },
    )
    root = data.get("법령") or {}
    basic = root.get("기본정보") or {}
    units = as_list((root.get("조문") or {}).get("조문단위"))

    ministry = basic.get("소관부처")
    ministry_name = ministry.get("content") if isinstance(ministry, dict) else (law.get("ministry") or "")
    law_kind = basic.get("법종구분")
    kind_name = (
        law_kind.get("content")
        if isinstance(law_kind, dict)
        else (law.get("lawKind") or "")
    )
    law_name = basic.get("법령명_한글") or law.get("lawName") or ""
    category = classify_law_kind(kind_name, law_name)
    effective = format_date(basic.get("시행일자") or law.get("effectiveDate"))
    promulgated = format_date(basic.get("공포일자") or law.get("promulgationDate"))

    # 호출측 instruments에 시행일 등이 반영되도록 갱신
    law["lawName"] = law_name
    law["lawKind"] = kind_name or law.get("lawKind") or ""
    law["category"] = category
    law["ministry"] = ministry_name or law.get("ministry") or ""
    law["effectiveDate"] = effective
    law["promulgationDate"] = promulgated
    if law_name:
        law["detailUrl"] = f"https://www.law.go.kr/법령/{law_name}"

    def collect(match_tokens: list[str]) -> list[dict[str, Any]]:
        matched: list[dict[str, Any]] = []
        for unit in units:
            if not isinstance(unit, dict):
                continue
            jo_flag = unit.get("조문여부")
            if jo_flag and jo_flag != "조문":
                continue

            blocks = build_article_blocks(unit)
            content = blocks_to_plain_text(blocks)
            title = unit.get("조문제목") or ""
            has_image = any(b.get("type") == "image" for b in blocks)
            if not content and not title and not has_image:
                continue

            # 법령명은 매칭에서 제외해 모든 조문이 히트되는 것을 방지
            haystack = f"{title}\n{content}"
            if match_tokens and not text_matches(haystack, match_tokens, full_query=full_query):
                continue

            article_no = unit.get("조문번호")
            branch = unit.get("조문가지번호") or "0"
            matched.append(
                normalize_article(
                    {
                        "법령ID": law["lawId"],
                        "법령일련번호": law.get("mst"),
                        "법령명": law_name,
                        "법령종류명": kind_name,
                        "소관부처명": ministry_name,
                        "조문번호": article_no,
                        "조문가지번호": branch,
                        "조문제목": title,
                        "조문내용": content,
                        "contentBlocks": blocks,
                        "시행일자": unit.get("조문시행일자") or effective,
                        "공포일자": promulgated,
                    },
                    fallback_category=category,
                )
            )
            if len(matched) >= max_articles:
                break
        return matched

    matched = collect(tokens)
    if fallback_primary and len(matched) < 8 and len(tokens) >= 2:
        primary = primary_keyword(full_query or " ".join(tokens), tokens)
        extra = collect([primary])
        seen = {(a["lawId"], a["joParam"]) for a in matched}
        for article in extra:
            key = (article["lawId"], article["joParam"])
            if key in seen:
                continue
            matched.append(article)
            seen.add(key)
            if len(matched) >= max_articles:
                break
    return matched


def sort_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"법률": 0, "시행령": 1, "시행규칙": 2, "기타": 3}
    articles.sort(
        key=lambda a: (
            priority.get(a["category"], 9),
            a["lawName"],
            a["sortKey"],
        )
    )
    return articles


def dedupe_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for article in articles:
        key = (article["lawId"], article["joParam"])
        if key in seen:
            continue
        seen.add(key)
        result.append(article)
    return result


def group_articles(articles: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "법률": [],
        "시행령": [],
        "시행규칙": [],
        "기타": [],
    }
    for article in articles:
        groups.setdefault(article["category"], []).append(article)
    for key in groups:
        groups[key] = sort_articles(groups[key])
    return groups


def score_law(law: dict[str, Any], query: str, primary: str) -> tuple:
    name = law.get("lawName") or ""
    category = law.get("category") or "기타"
    cat_rank = {"법률": 0, "시행령": 1, "시행규칙": 2}.get(category, 9)
    name_rank = 0
    if query and query in name:
        name_rank = 0
    elif primary and primary in name:
        name_rank = 1
    else:
        name_rank = 2
    # Prefer shorter, exact statute titles
    return (cat_rank, name_rank, 0 if category == "법률" else 1, len(name))


def merge_laws(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for group in groups:
        for law in group:
            law_id = law.get("lawId")
            if not law_id or law_id in seen:
                continue
            seen.add(law_id)
            result.append(law)
    return result


def pick_companion_laws(
    base: dict[str, Any],
    related: dict[str, Any] | None,
) -> dict[str, dict[str, Any] | None]:
    """선택된 법률에 대응하는 시행령·시행규칙을 고른다."""
    base_name = (base.get("lawName") or "").strip()
    expected_decree = f"{base_name} 시행령"
    expected_rule = f"{base_name} 시행규칙"

    decrees: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []

    if related:
        for item in related.get("related") or []:
            name = item.get("lawName") or ""
            category = item.get("category") or classify_law_kind("", name)
            packed = {
                "lawId": item["lawId"],
                "lawName": name,
                "lawKind": "",
                "category": category,
                "ministry": "",
                "mst": "",
                "detailUrl": item.get("detailUrl") or f"https://www.law.go.kr/법령/{name}",
            }
            if category == "시행령" or "시행령" in name:
                decrees.append(packed)
            elif category == "시행규칙" or "시행규칙" in name:
                rules.append(packed)

    def best_match(items: list[dict[str, Any]], exact_name: str) -> dict[str, Any] | None:
        if not items:
            return None
        exact = next((x for x in items if x["lawName"] == exact_name), None)
        if exact:
            return exact
        # 기준 법률명이 포함된 하위법령만 채택
        named = [x for x in items if base_name and base_name in x["lawName"]]
        if named:
            named.sort(key=lambda x: len(x["lawName"]))
            return named[0]
        return None

    return {
        "법률": base,
        "시행령": best_match(decrees, expected_decree),
        "시행규칙": best_match(rules, expected_rule),
        "extraRules": [
            x
            for x in rules
            if base_name and base_name in x["lawName"] and x["lawName"] != expected_rule
        ][:5],
    }


async def search_law_list(query: str, display: int = 30) -> list[dict[str, Any]]:
    """키워드와 관련된 법령(우선 법률) 목록을 반환한다."""
    tokens = query_tokens(query)
    primary = primary_keyword(query, tokens)

    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True) as client:
        tasks = [
            search_ai_articles(client, query, min(display, 40)),
            search_laws(client, query, search=1, display=15),
            search_laws(client, primary, search=1, display=20),
            search_laws(client, query, search=2, display=20),
            search_laws(client, primary, search=2, display=20),
        ]
        for token in [t for t in tokens if t != primary][:2]:
            tasks.append(search_laws(client, token, search=1, display=10))

        results = await asyncio.gather(*tasks)
        ai_articles = results[0]
        name_hits = merge_laws(*results[1:3], *results[5:])
        body_hits = merge_laws(results[3], results[4])

    # AI 검색 결과에서 등장한 법령도 목록에 반영
    from_ai: list[dict[str, Any]] = []
    seen_ai: set[str] = set()
    for article in ai_articles:
        law_id = article.get("lawId")
        if not law_id or law_id in seen_ai:
            continue
        seen_ai.add(law_id)
        from_ai.append(
            {
                "lawId": law_id,
                "mst": article.get("mst") or "",
                "lawName": article.get("lawName") or "",
                "lawKind": article.get("lawKind") or "",
                "category": article.get("category") or "기타",
                "ministry": article.get("ministry") or "",
                "effectiveDate": article.get("effectiveDate") or "",
                "promulgationDate": article.get("promulgationDate") or "",
                "detailUrl": article.get("detailUrl") or "",
                "hitCount": 1,
            }
        )

    # hitCount 집계
    hit_counts: dict[str, int] = {}
    for article in ai_articles:
        lid = article.get("lawId")
        if lid:
            hit_counts[lid] = hit_counts.get(lid, 0) + 1

    laws = merge_laws(name_hits, from_ai, body_hits)
    for law in laws:
        law["hitCount"] = hit_counts.get(law["lawId"], 0)

    # 법률을 먼저, 그다음 관련도·이름 순
    laws.sort(key=lambda law: (*score_law(law, query, primary), -law.get("hitCount", 0)))

    # 화면에 법률을 우선 노출하되, 법률이 너무 적으면 시행령/규칙도 포함
    statutes = [law for law in laws if law["category"] == "법률"]
    others = [law for law in laws if law["category"] != "법률"]
    ordered = statutes + others
    return ordered[:display]


async def resolve_law_by_id(
    client: httpx.AsyncClient,
    law_id: str,
    law_name: str = "",
) -> dict[str, Any]:
    law_id = str(law_id).zfill(6)
    if law_name:
        hits = await search_laws(client, law_name, search=1, display=10)
        for hit in hits:
            if hit["lawId"] == law_id or hit["lawName"] == law_name:
                return hit

    # ID로 본문 기본정보 조회
    data = await fetch_json(
        client,
        "lawService.do",
        {"target": "eflaw", "ID": law_id},
    )
    root = data.get("법령") or {}
    basic = root.get("기본정보") or {}
    ministry = basic.get("소관부처")
    ministry_name = ministry.get("content") if isinstance(ministry, dict) else ""
    law_kind = basic.get("법종구분")
    kind_name = law_kind.get("content") if isinstance(law_kind, dict) else ""
    name = basic.get("법령명_한글") or law_name
    return {
        "lawId": str(basic.get("법령ID") or law_id).zfill(6),
        "mst": "",
        "lawName": name,
        "lawKind": kind_name,
        "category": classify_law_kind(kind_name, name),
        "ministry": ministry_name,
        "effectiveDate": format_date(basic.get("시행일자")),
        "promulgationDate": format_date(basic.get("공포일자")),
        "detailUrl": f"https://www.law.go.kr/법령/{name}",
    }


def infer_parent_statute_name(law_name: str) -> str:
    """시행령·시행규칙 이름에서 상위 법률명 후보를 추정한다."""
    name = (law_name or "").strip()
    if not name:
        return ""
    patterns = [
        r"\s*시행규칙$",
        r"\s*시행령$",
        r"\s*에\s*관한\s*규칙$",
        r"\s*규칙$",
    ]
    candidate = name
    for pattern in patterns:
        next_name = re.sub(pattern, "", candidate).strip()
        if next_name and next_name != candidate:
            candidate = next_name
            break
    return candidate or name


def is_statute_like(law: dict[str, Any] | None) -> bool:
    if not law:
        return False
    name = (law.get("lawName") or "").strip()
    category = law.get("category") or classify_law_kind(law.get("lawKind") or "", name)
    if category == "법률":
        return True
    return bool(name.endswith("법") and "시행" not in name and "규칙" not in name)


async def resolve_companions(
    client: httpx.AsyncClient,
    law_id: str,
    law_name: str = "",
) -> tuple[dict[str, dict[str, Any] | None], dict[str, Any] | None]:
    """선택 법령의 법률·시행령·시행규칙 묶음을 해석한다.

    시행령/시행규칙을 선택해도 상위 법률과 대응 하위법령을 함께 채운다.
    """
    selected = await resolve_law_by_id(client, law_id, law_name)
    selected_category = selected.get("category") or classify_law_kind(
        selected.get("lawKind") or "", selected.get("lawName") or ""
    )
    selected["category"] = selected_category

    # 1) 관련법령 API로 묶음/상위 법률 찾기
    query_names: list[str] = []
    for name in (
        selected.get("lawName") or "",
        infer_parent_statute_name(selected.get("lawName") or ""),
        law_name,
    ):
        cleaned = (name or "").strip()
        if cleaned and cleaned not in query_names:
            query_names.append(cleaned)

    related = None
    for query_name in query_names:
        try:
            related = await fetch_related_laws(client, query_name)
        except Exception:  # noqa: BLE001
            related = None
        if related and (related.get("baseLawName") or related.get("related")):
            break

    # 2) 3단의 기준은 항상 법률
    base = selected
    if selected_category != "법률":
        parent = None
        if related and related.get("baseLawName") and is_statute_like(
            {
                "lawName": related.get("baseLawName") or "",
                "category": classify_law_kind("", related.get("baseLawName") or ""),
            }
        ):
            parent = {
                "lawId": related.get("baseLawId") or "",
                "lawName": related.get("baseLawName") or "",
            }
        if not parent and related:
            for item in related.get("related") or []:
                if is_statute_like(item):
                    parent = item
                    break
        if not parent:
            parent_name = infer_parent_statute_name(selected.get("lawName") or "")
            if parent_name and parent_name != selected.get("lawName"):
                parent_hits = await search_laws(client, parent_name, search=1, display=10)
                for hit in parent_hits:
                    if is_statute_like(hit) and (
                        hit["lawName"] == parent_name or parent_name in hit["lawName"]
                    ):
                        parent = hit
                        break
                if not parent:
                    for hit in parent_hits:
                        if is_statute_like(hit):
                            parent = hit
                            break
        if parent and parent.get("lawId"):
            base = await resolve_law_by_id(
                client,
                str(parent.get("lawId")),
                parent.get("lawName") or "",
            )
            try:
                related = await fetch_related_laws(client, base["lawName"]) or related
            except Exception:  # noqa: BLE001
                pass

    companions = pick_companion_laws(base, related)

    # 3) 사용자가 고른 법령은 해당 칸에 반드시 유지
    if selected_category == "법률":
        companions["법률"] = selected
    elif selected_category == "시행령":
        companions["법률"] = companions.get("법률") or base
        companions["시행령"] = selected
    elif selected_category == "시행규칙":
        companions["법률"] = companions.get("법률") if is_statute_like(companions.get("법률")) else base
        companions["시행규칙"] = selected
        if not is_statute_like(companions.get("법률")) and is_statute_like(base):
            companions["법률"] = base

    # 기준 법률이 비정상인 경우 보정
    if not is_statute_like(companions.get("법률")) and is_statute_like(base):
        companions["법률"] = base

    statute = companions.get("법률")
    statute_name = (statute or {}).get("lawName") or (base.get("lawName") if base else "") or ""

    # 4) 이름 검색으로 빈 칸 보완 (선택 칸은 덮어쓰지 않음)
    if not companions.get("시행령") and statute_name:
        decree_hits = await search_laws(client, f"{statute_name} 시행령", search=1, display=8)
        for hit in decree_hits:
            if hit["category"] == "시행령" or "시행령" in hit["lawName"]:
                companions["시행령"] = hit
                break
    if not companions.get("시행규칙") and statute_name:
        rule_hits = await search_laws(client, f"{statute_name} 시행규칙", search=1, display=8)
        for hit in rule_hits:
            if hit["category"] == "시행규칙" or "시행규칙" in hit["lawName"]:
                companions["시행규칙"] = hit
                break

    # 선택 규칙/령이 검색 보완 과정에서 빠지지 않게 한 번 더 고정
    if selected_category == "시행령":
        companions["시행령"] = selected
    elif selected_category == "시행규칙":
        companions["시행규칙"] = selected

    return companions, related


async def _load_instrument_column(
    client: httpx.AsyncClient,
    label: str,
    law: dict[str, Any] | None,
    *,
    tokens: list[str],
    full_query: str,
    max_articles: int,
    fallback_primary: bool,
) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
    if not law:
        return label, [], None
    articles = await fetch_law_articles(
        client,
        law,
        tokens,
        full_query=full_query,
        max_articles=max_articles,
        fallback_primary=fallback_primary,
    )
    articles = sort_articles(dedupe_articles(articles))
    try:
        law["currency"] = await assess_instrument_currency(client, law)
    except Exception as exc:  # noqa: BLE001
        law["currency"] = {
            "code": "unknown",
            "label": "현행 여부 확인 불가",
            "detail": f"확인 중 오류: {exc}",
            "isInForce": False,
            "isLatestCurrent": False,
            "upcoming": [],
            "current": None,
            "loaded": {
                "mst": law.get("mst") or "",
                "effectiveDate": law.get("effectiveDate") or "",
                "promulgationDate": law.get("promulgationDate") or "",
            },
            "checkedAt": today_kst().isoformat(),
        }
    return label, articles, law


async def compare_three_tier(
    query: str,
    law_id: str,
    law_name: str = "",
    max_articles: int = 40,
) -> dict[str, Any]:
    """선택한 법률과 관련 시행령·시행규칙의 관련 조문을 3단으로 반환."""
    tokens = query_tokens(query)

    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True) as client:
        companions, related = await resolve_companions(client, law_id, law_name)
        targets = [
            ("법률", companions["법률"]),
            ("시행령", companions["시행령"]),
            ("시행규칙", companions["시행규칙"]),
        ]
        columns_raw = await asyncio.gather(
            *[
                _load_instrument_column(
                    client,
                    label,
                    law,
                    tokens=tokens,
                    full_query=query,
                    max_articles=max_articles,
                    fallback_primary=True,
                )
                for label, law in targets
            ]
        )

    columns: dict[str, list[dict[str, Any]]] = {"법률": [], "시행령": [], "시행규칙": []}
    instruments: dict[str, dict[str, Any] | None] = {
        "법률": companions["법률"],
        "시행령": companions["시행령"],
        "시행규칙": companions["시행규칙"],
    }
    for label, articles, law in columns_raw:
        columns[label] = articles
        if law:
            instruments[label] = law

    total = sum(len(v) for v in columns.values())
    return {
        "query": query,
        "mode": "search",
        "baseLaw": companions["법률"],
        "instruments": instruments,
        "columns": columns,
        "total": total,
        "relatedLaws": related,
    }


async def compare_three_tier_full(
    law_id: str,
    law_name: str = "",
    max_articles: int = 3000,
) -> dict[str, Any]:
    """선택한 법률·시행령·시행규칙의 전체 조문을 3단으로 반환(키워드 필터 없음)."""
    async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True) as client:
        companions, related = await resolve_companions(client, law_id, law_name)
        targets = [
            ("법률", companions["법률"]),
            ("시행령", companions["시행령"]),
            ("시행규칙", companions["시행규칙"]),
        ]
        columns_raw = await asyncio.gather(
            *[
                _load_instrument_column(
                    client,
                    label,
                    law,
                    tokens=[],
                    full_query="",
                    max_articles=max_articles,
                    fallback_primary=False,
                )
                for label, law in targets
            ]
        )

    columns: dict[str, list[dict[str, Any]]] = {"법률": [], "시행령": [], "시행규칙": []}
    instruments: dict[str, dict[str, Any] | None] = {
        "법률": companions["법률"],
        "시행령": companions["시행령"],
        "시행규칙": companions["시행규칙"],
    }
    for label, articles, law in columns_raw:
        columns[label] = articles
        if law:
            instruments[label] = law

    total = sum(len(v) for v in columns.values())
    return {
        "query": "전체 조문",
        "mode": "full",
        "baseLaw": companions["법률"],
        "instruments": instruments,
        "columns": columns,
        "total": total,
        "relatedLaws": related,
    }
