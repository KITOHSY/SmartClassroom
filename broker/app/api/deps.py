"""API 의존성.

- get_db: AsyncSession yield (T03부터 노출)
- get_current_user: 인증 필수 — 미인증 시 UnauthenticatedError raise
  (errors.py 핸들러가 Accept 분기 응답으로 변환)
- get_optional_user: 인증 선택 — None 허용
- require_admin: admin role 강제 (HTTP 403)
"""

from __future__ import annotations

from broker.app.core.auth_responses import UnauthenticatedError
from broker.app.core.config import get_settings
from broker.app.domain.user import User
from broker.app.infra.db import get_db
from broker.app.providers import get_active_provider
from fastapi import Depends, HTTPException, Request, status

__all__ = ["get_current_user", "get_db", "get_optional_user", "require_admin"]


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
