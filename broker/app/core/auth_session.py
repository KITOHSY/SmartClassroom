"""Broker 세션 토큰 — 서버사이드 opaque 세션.

쿠키 raw 값(URL-safe Base64 32바이트)은 클라이언트에게만 전달.
DB에는 sha256(raw) 64자만 저장 — DB 덤프 유출 시 세션 재현 불가.
T03 `tokens` 테이블에 `purpose='session'`으로 적재해 동일 테이블/인덱스 재사용.

SLO(Single Logout) 백본 = `revoke_all_sessions_for_user(user_id)`.
T04b의 PMI-SSO 로그아웃 수신 엔드포인트가 이 헬퍼만 호출하도록 격리한다.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast

from broker.app.domain.token import Token
from broker.app.domain.user import User
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

SESSION_PURPOSE = "session"


def _hash_cookie(raw_cookie: str) -> str:
    return hashlib.sha256(raw_cookie.encode("utf-8")).hexdigest()


async def issue_session(
    session: AsyncSession,
    user: User,
    *,
    ttl_seconds: int,
) -> tuple[str, Token]:
    """세션 발급. (raw_cookie, Token) 반환. commit은 호출자 책임."""
    raw_cookie = secrets.token_urlsafe(32)
    jti = _hash_cookie(raw_cookie)
    now = datetime.now(UTC)
    token = Token(
        jti=jti,
        user_id=user.id,
        host_id=None,
        reservation_id=None,
        purpose=SESSION_PURPOSE,
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    session.add(token)
    await session.flush()
    return raw_cookie, token


async def verify_session(session: AsyncSession, raw_cookie: str) -> User | None:
    """쿠키 raw → User. 만료/회수/위조/누락 모두 None."""
    if not raw_cookie:
        return None
    jti = _hash_cookie(raw_cookie)
    now = datetime.now(UTC)
    stmt = (
        select(User)
        .join(Token, Token.user_id == User.id)
        .where(
            Token.jti == jti,
            Token.purpose == SESSION_PURPOSE,
            Token.revoked_at.is_(None),
            Token.consumed_at.is_(None),
            Token.expires_at > now,
            User.is_active.is_(True),
        )
    )
    return cast("User | None", await session.scalar(stmt))


async def revoke_session(session: AsyncSession, raw_cookie: str) -> int:
    """본인 세션 단일 revoke. 영향 행 수 반환. commit은 호출자 책임."""
    if not raw_cookie:
        return 0
    jti = _hash_cookie(raw_cookie)
    now = datetime.now(UTC)
    stmt = (
        update(Token)
        .where(
            Token.jti == jti,
            Token.purpose == SESSION_PURPOSE,
            Token.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    result = await session.execute(stmt)
    return cast(int, getattr(result, "rowcount", 0)) or 0


async def revoke_all_sessions_for_user(session: AsyncSession, user_id: int) -> int:
    """SLO 백본 — 사용자의 모든 활성 세션을 일괄 revoke. commit은 호출자 책임."""
    now = datetime.now(UTC)
    stmt = (
        update(Token)
        .where(
            Token.user_id == user_id,
            Token.purpose == SESSION_PURPOSE,
            Token.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    result = await session.execute(stmt)
    return cast(int, getattr(result, "rowcount", 0)) or 0
