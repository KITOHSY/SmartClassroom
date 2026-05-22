"""API 의존성.

- get_db: AsyncSession yield (T03부터 노출)
- get_current_user: 인증 필수 — 미인증 시 UnauthenticatedError raise
  (errors.py 핸들러가 Accept 분기 응답으로 변환)
- get_optional_user: 인증 선택 — None 허용
- require_admin: admin role 강제 (HTTP 403)
- require_internal_token: X-Internal-Token 헤더 강제 — 내부 컴포넌트 전용 (T08, §11 A6)
- get_agent_host: Bearer agent token 검증 → (Host, Token) 반환 (T11)
"""

from __future__ import annotations

import hmac

from broker.app.core.auth_responses import UnauthenticatedError
from broker.app.core.config import get_settings
from broker.app.domain.host import Host
from broker.app.domain.token import Token
from broker.app.domain.user import User
from broker.app.infra.db import get_db
from broker.app.providers import get_active_provider
from broker.app.services.agent_token_service import verify_agent_token
from broker.app.services.host_events import HostEventBroker
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "get_agent_host",
    "get_current_user",
    "get_db",
    "get_host_event_broker",
    "get_optional_user",
    "require_admin",
    "require_internal_token",
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


async def require_internal_token(request: Request) -> None:
    """T08 (§11 A6) — 내부 컴포넌트 전용 X-Internal-Token 헤더 검증.

    `/tokens/verify` 등 머신-투-머신 엔드포인트 보호. 사용자 세션쿠키·admin·에이전트
    Bearer와 무관한 별도 인증 채널. `settings.internal_api_token`과 상수시간 비교하며,
    토큰 미설정 시 fail-closed(401). 호출자(Sunshine fork 등)가 단순 분기하도록 401만 사용.
    """
    settings = get_settings()
    expected = settings.internal_api_token
    provided = request.headers.get("x-internal-token", "")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_internal_token",
                "message": "유효한 X-Internal-Token 헤더가 필요합니다",
            },
        )


async def get_host_event_broker(request: Request) -> HostEventBroker:
    """T06 — lifespan에서 만든 단일 broker 인스턴스 주입.

    테스트(`client_no_lifespan`)는 lifespan을 안 돌리므로 이 의존성 사용 라우트는
    `client` fixture(LifespanManager) 사용 필수.
    """
    broker: HostEventBroker | None = getattr(request.app.state, "host_event_broker", None)
    if broker is None:
        # 안전망 — lifespan이 set 안 한 환경에서도 publish noop 인스턴스 제공.
        broker = HostEventBroker()
        request.app.state.host_event_broker = broker
    return broker


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
