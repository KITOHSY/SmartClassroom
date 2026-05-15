"""API 의존성.

- get_db: AsyncSession yield (T03부터 노출)
- get_current_user: 인증 필수 — 미인증 시 UnauthenticatedError raise
  (errors.py 핸들러가 Accept 분기 응답으로 변환)
- get_optional_user: 인증 선택 — None 허용
- require_admin: admin role 강제 (HTTP 403)
- get_agent_host: Bearer agent token 검증 → (Host, Token) 반환 (T11)
"""

from __future__ import annotations

from broker.app.core.auth_responses import UnauthenticatedError
from broker.app.core.config import get_settings
from broker.app.domain.host import Host
from broker.app.domain.token import Token
from broker.app.domain.user import User
from broker.app.infra.db import get_db
from broker.app.providers import get_active_provider
from broker.app.services.agent_token_service import verify_agent_token
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "get_agent_host",
    "get_current_user",
    "get_db",
    "get_optional_user",
    "require_admin",
]


async def get_current_user(request: Request) -> User:
    user: User | None = getattr(request.state, "user", None)
    if user is None:
        settings = get_settings()
        try:
            provider = get_active_provider(settings)
            login_url = await provider.initiate_login(request)
        except NotImplementedError:
            login_url = settings.auth_login_path
        raise UnauthenticatedError(login_url)
    return user


async def get_optional_user(request: Request) -> User | None:
    user: User | None = getattr(request.state, "user", None)
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한 필요")
    return user


async def get_agent_host(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> tuple[Host, Token]:
    """T11 — Authorization: Bearer <agent_token> → (Host, Token) 반환.

    실패 케이스 모두 401 + 통일 코드:
    - missing_bearer: Authorization 헤더 부재/형식 불일치
    - invalid_agent_token: 위조/만료/회수/소비완료
    - host_missing: 토큰은 valid지만 host 행이 사라짐(이론상 안 일어남 — 안전망)
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_bearer", "message": "Authorization: Bearer <token> 필요"},
        )
    raw_token = auth_header[7:].strip()
    token = await verify_agent_token(db, raw_token)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_agent_token", "message": "유효하지 않은 에이전트 토큰"},
        )
    host = await db.get(Host, token.host_id)
    if host is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "host_missing", "message": "토큰의 호스트가 사라졌습니다"},
        )
    return host, token
