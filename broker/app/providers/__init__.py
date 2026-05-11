"""Auth Provider 팩토리.

운영 가드(`APP_ENV=production AND AUTH_PROVIDER=mock` 차단)는
`broker.app.main._enforce_production_guards`에서 부팅 시 일괄 처리.
이 모듈은 settings.auth_provider 값에 따라 구체 Provider를 반환.
"""

from __future__ import annotations

from functools import lru_cache

from broker.app.core.auth import AuthProvider
from broker.app.core.config import Settings
from broker.app.providers.cnu_sso import CnuSsoProvider
from broker.app.providers.mock import MockAuthProvider


@lru_cache(maxsize=4)
def _build_provider(name: str) -> AuthProvider:
    if name == "mock":
        return MockAuthProvider()
    if name == "cnu_sso":
        return CnuSsoProvider()
    raise RuntimeError(f"지원하지 않는 AUTH_PROVIDER 값입니다: {name}")


def get_active_provider(settings: Settings) -> AuthProvider:
    return _build_provider(settings.auth_provider)


__all__ = ["get_active_provider"]
