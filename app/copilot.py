from __future__ import annotations

import os
from typing import Any

import httpx

ANTHROPIC_URL = os.getenv(
    "ANTHROPIC_BASE_URL",
    "https://api.anthropic.com/v1/messages",
).strip()
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01").strip()
DEFAULT_MODEL = os.getenv("COPILOT_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"))


def get_copilot_key() -> str:
    return (
        os.getenv("COPILOT_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or ""
    ).strip()


def build_search_context(payload: dict[str, Any], *, max_chars: int = 14000) -> str:
    """검색된 3단 조문을 Copilot 컨텍스트 문자열로 만든다."""
    lines: list[str] = []
    query = payload.get("query") or ""
    base = payload.get("baseLaw") or {}
    lines.append(f"검색어: {query}")
    lines.append(f"기준 법률: {base.get('lawName') or ''}")
    lines.append("")

    columns = payload.get("columns") or {}
    instruments = payload.get("instruments") or {}
    for cat in ("법률", "시행령", "시행규칙"):
        instrument = instruments.get(cat) or {}
        articles = columns.get(cat) or []
        currency = (instrument.get("currency") or {}).get("label") or ""
        lines.append(f"## {cat}: {instrument.get('lawName') or '없음'}")
        if instrument.get("effectiveDate"):
            lines.append(f"- 시행일: {instrument.get('effectiveDate')}")
        if currency:
            lines.append(f"- 현행 여부: {currency}")
        if not articles:
            lines.append("- 관련 조문 없음")
            lines.append("")
            continue
        for article in articles[:20]:
            label = article.get("articleLabel") or ""
            title = article.get("articleTitle") or ""
            content = (article.get("articleContent") or "").strip()
            head = f"{label}" + (f"({title})" if title else "")
            lines.append(f"### {head}")
            if content:
                lines.append(content[:1200])
            lines.append("")
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n\n...(이하 생략)"
    return text


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts).strip()


async def ask_copilot(
    *,
    question: str,
    context: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    api_key = get_copilot_key()
    if not api_key:
        raise RuntimeError(
            "COPILOT_API_KEY(또는 ANTHROPIC_API_KEY)가 설정되지 않았습니다. "
            ".env 파일에 Anthropic API 키를 넣어 주세요."
        )

    system = (
        "당신은 대한민국 법령 해석 보조 AI입니다. "
        "아래 제공된 검색 결과(법률·시행령·시행규칙 조문)를 근거로 한국어로 답하세요. "
        "조문을 인용할 때는 법령명과 조문번호를 밝히세요. "
        "검색 결과에 없는 내용은 추측하지 말고, 일반론과 검색결과 근거를 구분하세요. "
        "법적 조언의 확정이 아니라 참고용 설명임을 필요 시 짧게 알리세요."
    )

    messages: list[dict[str, str]] = []
    for item in history or []:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    user_prompt = (
        "다음은 사용자가 검색한 법령 조문 결과입니다.\n\n"
        f"{context}\n\n"
        "---\n"
        f"사용자 질문: {question.strip()}"
    )
    messages.append({"role": "user", "content": user_prompt})

    # Anthropic Messages API는 user/assistant가 번갈아 와야 함
    normalized: list[dict[str, str]] = []
    for msg in messages:
        if normalized and normalized[-1]["role"] == msg["role"]:
            normalized[-1]["content"] += "\n\n" + msg["content"]
        else:
            normalized.append(dict(msg))
    if normalized and normalized[0]["role"] != "user":
        normalized.insert(0, {"role": "user", "content": "(이전 대화 이어가기)"})

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    body = {
        "model": DEFAULT_MODEL,
        "max_tokens": 1600,
        "temperature": 0.2,
        "system": system,
        "messages": normalized,
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(ANTHROPIC_URL, headers=headers, json=body)
        if response.status_code >= 400:
            detail = response.text[:500]
            raise RuntimeError(f"Claude API 오류 ({response.status_code}): {detail}")
        data = response.json()

    answer = _extract_text(data.get("content"))
    if not answer:
        answer = "(응답이 비어 있습니다.)"

    usage = data.get("usage") or {}
    return {
        "answer": answer,
        "model": data.get("model") or DEFAULT_MODEL,
        "usage": usage,
    }
