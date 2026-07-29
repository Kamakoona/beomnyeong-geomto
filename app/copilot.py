from __future__ import annotations

import os
from typing import Any

import httpx

OPENAI_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions").strip()
DEFAULT_MODEL = os.getenv("COPILOT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))


def get_copilot_key() -> str:
    return (
        os.getenv("COPILOT_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("AZURE_OPENAI_API_KEY")
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


async def ask_copilot(
    *,
    question: str,
    context: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    api_key = get_copilot_key()
    if not api_key:
        raise RuntimeError(
            "COPILOT_API_KEY(또는 OPENAI_API_KEY)가 설정되지 않았습니다. "
            ".env 파일에 OpenAI API 키를 넣어 주세요."
        )

    system = (
        "당신은 Microsoft Copilot 스타일의 대한민국 법령 해석 보조 AI입니다. "
        "아래 제공된 검색 결과(법률·시행령·시행규칙 조문)를 근거로 한국어로 답하세요. "
        "조문을 인용할 때는 법령명과 조문번호를 밝히세요. "
        "검색 결과에 없는 내용은 추측하지 말고, 일반론과 검색결과 근거를 구분하세요. "
        "법적 조언의 확정이 아니라 참고용 설명임을 필요 시 짧게 알리세요."
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1600,
    }

    # Azure OpenAI 사용 시
    azure_endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or ""
    azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION") or "2024-10-21"
    if azure_endpoint and azure_deployment:
        url = (
            f"{azure_endpoint}/openai/deployments/{azure_deployment}/chat/completions"
            f"?api-version={azure_api_version}"
        )
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        body = {
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1600,
        }
    else:
        url = OPENAI_URL

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            detail = response.text[:500]
            raise RuntimeError(f"Copilot(OpenAI) API 오류 ({response.status_code}): {detail}")
        data = response.json()

    choices = data.get("choices") or []
    answer = ""
    if choices:
        message = choices[0].get("message") or {}
        answer = (message.get("content") or "").strip()
    if not answer:
        answer = "(응답이 비어 있습니다.)"

    return {
        "answer": answer,
        "model": data.get("model") or DEFAULT_MODEL,
        "usage": data.get("usage") or {},
    }
