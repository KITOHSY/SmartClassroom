import time
import uuid

import structlog
from broker.app.core.auth_session import verify_session
from broker.app.core.config import get_settings
from broker.app.infra.db import get_session_factory
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=rid)
        try:
            response: Response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers[REQUEST_ID_HEADER] = rid
        return response


class AuthSessionMiddleware(BaseHTTPMiddleware):
    """쿠키 → 사용자 식별. 인증 강제는 dependency가 담당, 미들웨어는 식별만."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user = None
        bound = False
        settings = get_settings()
        raw = request.cookies.get(settings.session_cookie_name)
        if raw:
            factory = get_session_factory()
            async with factory() as db:
                user = await verify_session(db, raw)
            if user is not None:
                request.state.user = user
                structlog.contextvars.bind_contextvars(
                    user_id=user.id,
                    auth_provider=user.provider,
                )
                bound = True
        try:
            response: Response = await call_next(request)
        finally:
            if bound:
                structlog.contextvars.unbind_contextvars("user_id", "auth_provider")
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        log = structlog.get_logger("access")
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log.exception(
                "http.request.error",
                method=request.method,
                path=request.url.path,
                duration_ms=round(elapsed_ms, 2),
            )
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(elapsed_ms, 2),
            client_ip=request.client.host if request.client else None,
        )
        return response
