"""미인증 응답 생성 — Accept 헤더 분기.

규칙:
- `/api/*` 경로: 항상 401 JSON (SPA/도구 친화).
- 그 외 + `Accept: text/html`: 302 redirect to provider login URL.
- 그 외: 401 JSON.

ErrorResponse 포맷(core/errors.py)을 재사용해 응답 일관성 유지.
"""

from __future__ import annotations

from broker.app.core.errors import ErrorResponse
from fastapi import Request
from fastapi.responses import ORJSONResponse, RedirectResponse
from starlette import status
from starlette.responses import Response


class UnauthenticatedError(Exception):
    """인증 의존성이 raise. errors.py 핸들러가 Accept 분기 Response로 변환."""

    def __init__(self, login_url: str) -> None:
        super().__init__("unauthenticated")
        self.login_url = login_url


def _wants_html(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept


def _request_id(request: Request) -> str | None:
    return request.headers.get("X-Request-ID")


def unauthenticated_response(request: Request, login_url: str) -> Response:
    if _wants_html(request):
        return RedirectResponse(login_url, status_code=status.HTTP_302_FOUND)
    return ORJSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=ErrorResponse(
            error="unauthenticated",
            message="인증이 필요합니다",
            request_id=_request_id(request),
            detail={"login_url": login_url},
        ).model_dump(),
    )
