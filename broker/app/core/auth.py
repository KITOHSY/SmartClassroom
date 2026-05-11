"""AuthProvider 인터페이스 + UserIdentity 데이터 컨테이너.

T04a가 MockAuthProvider/CnuSsoProvider를 이 Protocol 위에 구현한다.
구체 구현은 broker.app.providers 하위에 위치.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import Request


@dataclass(frozen=True, slots=True)
class UserIdentity:
    external_id: str
    provider: str
    display_name: str
    email: str | None = None
    role: str = "user"


class AuthProvider(Protocol):
    name: str

    async def initiate_login(self, request: Request) -> str:
        """로그인 시작 — 302 destination URL 반환. 응답 객체 생성은 라우터 책임."""
        ...

    async def verify_callback(self, request: Request) -> UserIdentity:
        """콜백 요청 검증 → 사용자 식별 정보. 검증 실패는 ValueError로 raise."""
        ...

    async def fetch_user_identity(self, token: str) -> UserIdentity:
        """Provider-issued bearer 토큰 흐름용 — T07 동적 토큰과 무관."""
        ...
