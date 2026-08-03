from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.law_client import (
    HTTP_HEADERS,
    compare_three_tier_full,
    compare_three_tier,
    fetch_latest_article,
    search_law_list,
    search_ordinance_list,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
load_dotenv(BASE_DIR / ".env")

ASSET_REF_RE = re.compile(r'((?:href|src)=")(/static/[^"?]+)(")')


def _asset_version(rel_url: str) -> str:
    path = STATIC_DIR / rel_url.removeprefix("/static/")
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return "0"


def html_page(filename: str) -> HTMLResponse:
    """HTML을 내려줄 때 정적 자산 URL에 버전을 붙여 캐시를 무효화한다."""
    text = (STATIC_DIR / filename).read_text(encoding="utf-8")
    text = ASSET_REF_RE.sub(
        lambda m: f'{m.group(1)}{m.group(2)}?v={_asset_version(m.group(2))}{m.group(3)}',
        text,
    )
    return HTMLResponse(
        content=text,
        headers={
            "Cache-Control": "no-store, max-age=0, must-revalidate",
            "Pragma": "no-cache",
        },
    )


class StaticCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        elif path in {"/", "/law", "/ordin"}:
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
        return response


app = FastAPI(title="법제처 법령 조문 검색", version="1.3.0")
app.add_middleware(StaticCacheMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> HTMLResponse:
    return html_page("index.html")


@app.get("/law")
async def law_page() -> HTMLResponse:
    """선택한 법률 범위에서 다시 검색하는 새 탭 페이지."""
    return html_page("law.html")


@app.get("/ordin")
async def ordin_page() -> HTMLResponse:
    """자치법규 검색 결과 새 탭 페이지."""
    return html_page("ordin.html")


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "oc": os.getenv("LAW_API_OC", "test"),
        "version": app.version,
    }


@app.get("/api/law-image")
async def law_image(flSeq: str = Query(..., min_length=1, pattern=r"^\d+$")) -> Response:
    """국가법령정보센터 조문 이미지(수식·표) 프록시."""
    try:
        async with httpx.AsyncClient(headers=HTTP_HEADERS, follow_redirects=True, timeout=30.0) as client:
            response = await client.get(
                "https://www.law.go.kr/flDownload.do",
                params={"flSeq": flSeq},
            )
        if response.status_code >= 400 or not response.content:
            raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
        content_type = response.headers.get("content-type", "image/gif")
        # 일부 응답이 image/gif;;charset=UTF-8 형태
        content_type = content_type.split(";")[0].strip() or "image/gif"
        return Response(
            content=response.content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"이미지 조회 실패: {exc}") from exc


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=1, description="검색 키워드 또는 문장"),
    display: int = Query(30, ge=5, le=80),
) -> dict:
    """관련 조문이 있는 법령(법률 우선) 목록을 반환한다."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="검색어를 입력해 주세요.")

    try:
        laws = await search_law_list(query, display=display)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"법령 API 호출 실패: {exc}") from exc

    ordinances: list = []
    try:
        ordinances = await search_ordinance_list(query, display=30)
    except Exception:  # noqa: BLE001
        ordinances = []

    return {
        "query": query,
        "total": len(laws),
        "laws": laws,
        "ordinances": ordinances,
        "ordinanceTotal": len(ordinances),
        "source": "https://www.law.go.kr (법제처 국가법령정보센터 Open API)",
        "moleg": "https://www.moleg.go.kr",
    }


@app.get("/api/ordinances")
async def ordinances(
    q: str = Query(..., min_length=1, description="검색 키워드 또는 문장"),
    display: int = Query(30, ge=5, le=80),
) -> dict:
    """키워드가 포함된 자치법규 목록을 반환한다."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="검색어를 입력해 주세요.")

    try:
        items = await search_ordinance_list(query, display=display)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"자치법규 검색 실패: {exc}") from exc

    return {
        "query": query,
        "total": len(items),
        "ordinances": items,
        "source": "https://www.law.go.kr (자치법규 Open API)",
    }


@app.get("/api/compare")
async def compare(
    q: str = Query(..., min_length=1, description="검색 키워드 또는 문장"),
    law_id: str = Query(..., alias="lawId", min_length=1),
    law_name: str = Query("", alias="lawName"),
    max_articles: int = Query(40, ge=5, le=80, alias="maxArticles"),
) -> dict:
    """선택한 법률과 관련 시행령·시행규칙 조문을 3단으로 반환한다."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="검색어를 입력해 주세요.")

    try:
        result = await compare_three_tier(
            query,
            law_id=law_id,
            law_name=law_name,
            max_articles=max_articles,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"3단 조문 조회 실패: {exc}") from exc

    return result


@app.get("/api/compare-full")
async def compare_full(
    law_id: str = Query(..., alias="lawId", min_length=1),
    law_name: str = Query("", alias="lawName"),
    max_articles: int = Query(3000, ge=50, le=5000, alias="maxArticles"),
) -> dict:
    """선택한 법률·시행령·시행규칙의 전체 조문을 3단으로 반환한다."""
    try:
        result = await compare_three_tier_full(
            law_id=law_id,
            law_name=law_name,
            max_articles=max_articles,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"전체 조문 조회 실패: {exc}") from exc

    return result


@app.get("/api/article")
async def article(
    law_id: str = Query(..., alias="lawId"),
    jo: str = Query(..., min_length=6, max_length=6),
) -> dict:
    try:
        result = await fetch_latest_article(law_id, jo)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"조문 조회 실패: {exc}") from exc

    if not result:
        raise HTTPException(status_code=404, detail="조문을 찾을 수 없습니다.")
    return result
