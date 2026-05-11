"""CnuSsoProvider — T04b 슬롯.

PMI-SSO2 통합은 T04b에서 구현한다. 본 모듈은 import 가능성만 보장하고
실제 인스턴스 생성/메서드 호출은 NotImplementedError로 차단한다 —
APP_ENV/AUTH_PROVIDER 조합으로 부팅이 닿는 시점에 즉시 발견되도록.
"""

from __future__ import annotations

from broker.app.core.auth import UserIdentity
from fastapi import Request


class CnuSsoProvider:
    name = "cnu_sso"

    def __init__(self) -> None:
        raise NotImplementedError(
            "CnuSsoProvider는 T04b에서 구현됩니다. 현재는 AUTH_PROVIDER=mock으로 운영하세요."
        )

    async def initiate_login(self, request: Request) -> str:
        raise NotImplementedError

    async def verify_callback(self, request: Request) -> UserIdentity:
        raise NotImplementedError

    async def fetch_user_identity(self, token: str) -> UserIdentity:
        raise NotImplementedError
