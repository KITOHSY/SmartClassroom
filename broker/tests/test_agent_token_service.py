"""T11 agent_token_service 단위 테스트.

서비스 함수를 직접 호출 — `client` fixture로 lifespan/DATABASE_URL/alembic 보장.
세션은 `get_session_factory()`로 직접 발급 (T05 conftest `_insert_host` 패턴과 동일).
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator

import pytest_asyncio
from broker.app.services.agent_token_service import (
    AGENT_PURPOSE,
    issue_agent_token,
    revoke_active_agent_tokens,
    verify_agent_token,
)
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def db(client: AsyncClient) -> AsyncIterator[AsyncSession]:
    """lifespan 활성 client에 의존해 DB URL 보장 후 session 1개 발급."""
    _ = client
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


async def _seed_user_and_host(db: AsyncSession) -> tuple[int, int]:
    """admin user + host 한 쌍 시드. PK 튜플 반환."""
    import uuid

    suffix = uuid.uuid4().hex[:8]
    user_id_row = await db.execute(
        text(
            "INSERT INTO users (provider, external_id, display_name, role, is_active) "
            "VALUES ('mock', :ext, :name, 'admin', true) RETURNING id"
        ).bindparams(ext=f"admin-{suffix}", name=f"Admin {suffix}")
    )
    host_id_row = await db.execute(
        text(
            "INSERT INTO hosts (hostname, display_name, status) "
            "VALUES (:h, :d, 'OFFLINE') RETURNING id"
        ).bindparams(h=f"pc-{suffix}", d="시드 강의실 PC")
    )
    user_id: int = user_id_row.scalar_one()
    host_id: int = host_id_row.scalar_one()
    await db.commit()
    return user_id, host_id


async def test_issue_returns_raw_token_and_persists_only_hash(db: AsyncSession) -> None:
    """raw 토큰은 응답에만, DB jti는 sha256(raw) 64자 hex."""
    from broker.app.domain.host import Host
    from broker.app.domain.user import User

    user_id, host_id = await _seed_user_and_host(db)
    admin = await db.get(User, user_id)
    host = await db.get(Host, host_id)
    assert admin is not None and host is not None

    raw, token, revoked = await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()

    assert isinstance(raw, str) and len(raw) >= 32
    assert revoked == 0
    expected_jti = hashlib.sha256(raw.encode()).hexdigest()
    assert token.jti == expected_jti
    assert token.purpose == AGENT_PURPOSE
    assert token.host_id == host.id
    assert token.user_id == admin.id
    assert token.reservation_id is None
    assert token.consumed_at is None
    assert token.revoked_at is None


async def test_verify_happy_path(db: AsyncSession) -> None:
    from broker.app.domain.host import Host
    from broker.app.domain.user import User

    user_id, host_id = await _seed_user_and_host(db)
    admin = await db.get(User, user_id)
    host = await db.get(Host, host_id)
    assert admin is not None and host is not None

    raw, _, _ = await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()

    found = await verify_agent_token(db, raw)
    assert found is not None
    assert found.host_id == host.id
    assert found.purpose == AGENT_PURPOSE


async def test_verify_returns_none_after_revoke(db: AsyncSession) -> None:
    from broker.app.domain.host import Host
    from broker.app.domain.user import User

    user_id, host_id = await _seed_user_and_host(db)
    admin = await db.get(User, user_id)
    host = await db.get(Host, host_id)
    assert admin is not None and host is not None

    raw, _, _ = await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()
    revoked = await revoke_active_agent_tokens(db, host.id)
    await db.commit()
    assert revoked == 1

    assert await verify_agent_token(db, raw) is None
    assert await verify_agent_token(db, "") is None
    assert await verify_agent_token(db, "definitely-not-a-token") is None


async def test_revoke_idempotent(db: AsyncSession) -> None:
    """두 번째 revoke는 영향 행 0."""
    from broker.app.domain.host import Host
    from broker.app.domain.user import User

    user_id, host_id = await _seed_user_and_host(db)
    admin = await db.get(User, user_id)
    host = await db.get(Host, host_id)
    assert admin is not None and host is not None

    await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()
    first = await revoke_active_agent_tokens(db, host.id)
    await db.commit()
    second = await revoke_active_agent_tokens(db, host.id)
    await db.commit()
    assert first == 1
    assert second == 0


async def test_issue_revokes_previous_active(db: AsyncSession) -> None:
    """재발급 시 이전 활성 토큰은 자동 revoke — secret 회전 패턴."""
    from broker.app.domain.host import Host
    from broker.app.domain.user import User

    user_id, host_id = await _seed_user_and_host(db)
    admin = await db.get(User, user_id)
    host = await db.get(Host, host_id)
    assert admin is not None and host is not None

    raw_old, _, revoked_first = await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()
    assert revoked_first == 0

    raw_new, _, revoked_second = await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()
    assert revoked_second == 1
    assert raw_new != raw_old

    # 이전 토큰은 무효, 새 토큰은 유효
    assert await verify_agent_token(db, raw_old) is None
    assert await verify_agent_token(db, raw_new) is not None
