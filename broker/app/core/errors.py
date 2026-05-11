from typing import Any

from fastapi import FastAPI, HTTPException, Request
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
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="validation_error",
                message="요청 검증 실패",
                request_id=_request_id(request),
                detail={"errors": exc.errors()},
            ).model_dump(),
        )

    # UnauthenticatedError 핸들러는 import 시점에 자동 적재.
    from broker.app.core.auth_responses import UnauthenticatedError, unauthenticated_response

    @app.exception_handler(UnauthenticatedError)
    async def _unauth(request: Request, exc: UnauthenticatedError) -> Response:
        return unauthenticated_response(request, exc.login_url)

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
