from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field
from starlette import status
from starlette.responses import Response


class ErrorResponse(BaseModel):
    error: str = Field(..., description="에러 코드 (snake_case)")
    message: str = Field(..., description="사람이 읽을 메시지")
    request_id: str | None = Field(None, description="요청 추적 ID")
    detail: dict[str, Any] | None = None


# T05 예약 도메인 예외 — service가 raise, router가 HTTP 매핑.
class ReservationConflictError(Exception):
    """동일 호스트·시간 슬롯 중복 — EXCLUDE GIST 제약 위반 매핑."""

    def __init__(self, message: str = "동일 시간대에 이미 예약이 존재합니다") -> None:
        super().__init__(message)
        self.message = message


class ReservationQuotaError(Exception):
    """사용자 동시/일일 한도 초과."""

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class InvalidReservationWindowError(Exception):
    """30분 그리드 위반, 과거 시작, lookahead 초과, duration 초과, 시간 역전 등."""

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class InvalidConnectWindowError(Exception):
    """T07 접속 토큰 발급 게이트 위반 — too_early / expired_window / reservation_not_active."""

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


def _request_id(request: Request) -> str | None:
    return request.headers.get("X-Request-ID")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error="http_error",
                message=str(exc.detail),
                request_id=_request_id(request),
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError) -> ORJSONResponse:
        # Pydantic v2 errors may contain non-JSON primitives (datetime, bytes 등)
        # 'ctx'에 들어가는 input 값 — orjson은 못 직렬화해서 jsonable_encoder로 정규화.
        encoded_errors = jsonable_encoder(exc.errors())
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="validation_error",
                message="요청 검증 실패",
                request_id=_request_id(request),
                detail={"errors": encoded_errors},
            ).model_dump(),
        )

    # UnauthenticatedError 핸들러는 import 시점에 자동 적재.
    from broker.app.core.auth_responses import UnauthenticatedError, unauthenticated_response

    @app.exception_handler(UnauthenticatedError)
    async def _unauth(request: Request, exc: UnauthenticatedError) -> Response:
        return unauthenticated_response(request, exc.login_url)

    @app.exception_handler(ReservationConflictError)
    async def _reservation_conflict(
        request: Request, exc: ReservationConflictError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(
                error="reservation_conflict",
                message=exc.message,
                request_id=_request_id(request),
            ).model_dump(),
        )

    @app.exception_handler(ReservationQuotaError)
    async def _reservation_quota(
        request: Request, exc: ReservationQuotaError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=ErrorResponse(
                error="reservation_quota_exceeded",
                message=exc.message,
                request_id=_request_id(request),
                detail=exc.detail or None,
            ).model_dump(),
        )

    @app.exception_handler(InvalidReservationWindowError)
    async def _invalid_window(
        request: Request, exc: InvalidReservationWindowError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="invalid_reservation_window",
                message=exc.message,
                request_id=_request_id(request),
                detail=exc.detail or None,
            ).model_dump(),
        )

    @app.exception_handler(InvalidConnectWindowError)
    async def _invalid_connect_window(
        request: Request, exc: InvalidConnectWindowError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="invalid_connect_window",
                message=exc.message,
                request_id=_request_id(request),
                detail=exc.detail or None,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="internal_error",
                message="서버 내부 오류",
                request_id=_request_id(request),
            ).model_dump(),
        )
