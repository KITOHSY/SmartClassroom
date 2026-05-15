"""T11 에이전트 토큰 서비스.

`auth_session.py`/`token_service.py`의 sha256(raw) 패턴을 모델로 `purpose='agent'` Token 발급/검증.

설계 결정:
- raw 토큰은 발급 시 1회 응답에만 노출. DB는 `sha256(raw)` 64자 hex만 `jti` 컬럼에 저장.
- 같은 host의 활성 agent 토큰은 새 발급 직전 일괄 revoke (secret 교체 = 이전 토큰 무효).
- `expires_at = now + agent_token_ttl_days` (env 정책, 기본 3650일/10년).
- 1회 소비 안 함 — agent 토큰은 30초 주기 heartbeat에 매번 사용.
- user_id는 발급한 admin의 user_id 기록 (audit trail). host_id는 해당 호스트.
- commit은 호출자(router) 책임. 본 모듈은 add/execute/flush 만 수행.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Final, cast

from broker.app.core.config import get_settings
from broker.app.domain.host import Host
from broker.app.domain.token import Token
from broker.app.domain.user import User
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

AGENT_PURPOSE: Final[str] = "agent"


def _hash_raw(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def revoke_active_agent_tokens(db: AsyncSession, host_id: int) -> int:
    """주어진 host의 활성 agent 토큰 일괄 revoke. 새 발급 직전 호출.

    rowcount 반환. commit은 호출자 책임.
    `ix_tokens_active_expires` 부분 인덱스 hit (consumed_at IS NULL AND revoked_at IS NULL).
    """
    now = datetime.now(UTC)
    stmt = (
        update(Token)
        .where(
            Token.host_id == host_id,
            Token.purpose == AGENT_PURPOSE,
            Token.revoked_at.is_(None),
            Token.consumed_at.is_(None),
        )
        .values(revoked_at=now)
    )
    result = await db.execute(stmt)
    return cast(int, getattr(result, "rowcount", 0)) or 0


async def issue_agent_token(
    db: AsyncSession, *, host: Host, issued_by: User
) -> tuple[str, Token, int]:
    """에이전트 토큰 발급. (raw_token, Token, revoked_count) 반환.

    같은 host의 활성 agent 토큰을 일괄 revoke한 다음 새 토큰을 INSERT.
    같은 트랜잭션 내, commit은 라우터 책임.
    `issued_by`: 발급한 admin (audit trail, user_id 컬럼).
    """
    revoked_count = await revoke_active_agent_tokens(db, host.id)
    settings = get_settings()
    now = datetime.now(UTC)
    raw_token = secrets.token_urlsafe(32)
    jti = _hash_raw(raw_token)
    token = Token(
        jti=jti,
        user_id=issued_by.id,
        host_id=host.id,
        reservation_id=None,
        purpose=AGENT_PURPOSE,
        issued_at=now,
        expires_at=now + timedelta(days=settings.agent_token_ttl_days),
    )
    db.add(token)
    await db.flush()
    return raw_token, token, revoked_count


async def verify_agent_token(db: AsyncSession, raw_token: str) -> Token | None:
    """raw → Token. 만료/회수/위조/누락 모두 None.

    1회 소비 안 함 — agent 토큰은 다회 사용.
    Token만 select — host는 호출자가 명시 fetch (lazy load 회피).
    """
    if not raw_token:
        return None
    jti = _hash_raw(raw_token)
    now = datetime.now(UTC)
    stmt = select(Token).where(
        Token.jti == jti,
        Token.purpose == AGENT_PURPOSE,
        Token.revoked_at.is_(None),
        Token.consumed_at.is_(None),
        Token.expires_at > now,
    )
    return cast("Token | None", await db.scalar(stmt))
