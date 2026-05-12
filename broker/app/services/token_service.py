"""T07 동적 접속 토큰 서비스.

`auth_session.py`의 sha256(raw) 패턴을 모델로 `purpose='connect'` Token을 발급/검증.

설계 결정:
- raw 토큰은 발급 시 1회 응답에만 노출. DB는 `sha256(raw)`(64자)만 `jti` 컬럼에 저장.
- 같은 reservation의 활성 connect 토큰은 새 발급 직전 일괄 revoke (replay 강화).
- `expires_at = reservation.ends_at` — 예약 종료 = 토큰 자동 무효.
- 발급 게이트: `starts_at - grace ~ ends_at` (grace = settings.connect_token_grace_seconds).
- 1회 소비: `consumed_at IS NULL` predicate UPDATE rowcount==1 만 valid.
- commit은 호출자(router) 책임. 본 모듈은 add/execute/flush 만 수행.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Final, cast

from broker.app.core.config import get_settings
from broker.app.core.errors import InvalidConnectWindowError
from broker.app.domain.reservation import Reservation
from broker.app.domain.token import Token
from broker.app.domain.user import User
from broker.app.services.reservation import (
    _assert_can_access,
    reservation_bounds,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

CONNECT_PURPOSE: Final[str] = "connect"


def _hash_raw(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def revoke_active_tokens_for_reservation(db: AsyncSession, reservation_id: int) -> int:
    """같은 reservation의 활성(connect) 토큰 일괄 revoke. 새 발급 직전 호출.

    rowcount 반환. commit은 호출자 책임.
    `ix_tokens_active_expires` 부분 인덱스 hit (consumed_at IS NULL AND revoked_at IS NULL).
    """
    now = datetime.now(UTC)
    stmt = (
        update(Token)
        .where(
            Token.reservation_id == reservation_id,
            Token.purpose == CONNECT_PURPOSE,
            Token.revoked_at.is_(None),
            Token.consumed_at.is_(None),
        )
        .values(revoked_at=now)
    )
    result = await db.execute(stmt)
    return cast(int, getattr(result, "rowcount", 0)) or 0


async def issue_connect_token(
    db: AsyncSession, *, user: User, reservation: Reservation
) -> tuple[str, Token, int]:
    """접속 토큰 발급. (raw_token, Token, revoked_count) 반환.

    검증 통과 후 같은 reservation의 활성 connect 토큰을 일괄 revoke한 다음
    새 토큰을 INSERT한다. 같은 트랜잭션 내, commit은 라우터 책임.
    """
    # 권한 — 본인 또는 admin. 그 외는 NotOwnerError → 라우터에서 404 변환.
    _assert_can_access(reservation, user)

    if reservation.status != "CONFIRMED":
        raise InvalidConnectWindowError(
            "예약이 활성 상태가 아닙니다",
            detail={"reason": "reservation_not_active", "status": reservation.status},
        )

    starts_at, ends_at = reservation_bounds(reservation)
    settings = get_settings()
    now = datetime.now(UTC)
    grace = settings.connect_token_grace_seconds

    if now < starts_at - timedelta(seconds=grace):
        raise InvalidConnectWindowError(
            f"예약 시작 {grace}초 전부터 토큰을 발급할 수 있습니다",
            detail={
                "reason": "too_early",
                "starts_at": starts_at.isoformat(),
                "now": now.isoformat(),
                "grace_seconds": grace,
            },
        )
    if now >= ends_at:
        raise InvalidConnectWindowError(
            "예약 시간 윈도우가 종료되었습니다",
            detail={
                "reason": "expired_window",
                "ends_at": ends_at.isoformat(),
                "now": now.isoformat(),
            },
        )

    revoked_count = await revoke_active_tokens_for_reservation(db, reservation.id)

    raw_token = secrets.token_urlsafe(32)
    jti = _hash_raw(raw_token)
    token = Token(
        jti=jti,
        user_id=user.id,
        host_id=reservation.host_id,
        reservation_id=reservation.id,
        purpose=CONNECT_PURPOSE,
        issued_at=now,
        expires_at=ends_at,
    )
    db.add(token)
    await db.flush()
    return raw_token, token, revoked_count


async def verify_connect_token(db: AsyncSession, raw_token: str) -> Token | None:
    """raw → Token. 만료/회수/소비완료/위조/누락 모두 None.

    소비는 안 함. 호출자가 별도로 `mark_consumed`를 부른다.
    Token만 select — user/host는 호출자가 명시 fetch (lazy load 회피).
    """
    if not raw_token:
        return None
    jti = _hash_raw(raw_token)
    now = datetime.now(UTC)
    stmt = select(Token).where(
        Token.jti == jti,
        Token.purpose == CONNECT_PURPOSE,
        Token.revoked_at.is_(None),
        Token.consumed_at.is_(None),
        Token.expires_at > now,
    )
    return cast("Token | None", await db.scalar(stmt))


async def mark_consumed(db: AsyncSession, token: Token) -> bool:
    """1회 소비 마킹. consumed_at IS NULL 인 row만 UPDATE.

    rowcount==1이면 True (이번 호출이 소비), False면 다른 호출이 먼저 소비.
    DB-level 직렬화로 동시 verify 시 정확히 1번만 통과.
    """
    now = datetime.now(UTC)
    stmt = (
        update(Token)
        .where(
            Token.id == token.id,
            Token.consumed_at.is_(None),
            Token.revoked_at.is_(None),
        )
        .values(consumed_at=now)
    )
    result = await db.execute(stmt)
    rowcount = cast(int, getattr(result, "rowcount", 0)) or 0
    return rowcount == 1
