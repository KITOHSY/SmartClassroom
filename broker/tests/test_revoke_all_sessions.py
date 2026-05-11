"""세션 발급/검증/revoke + SLO 헬퍼 단위 테스트."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from broker.app.core.auth import UserIdentity
from broker.app.core.auth_session import (
    issue_session,
    revoke_all_sessions_for_user,
    revoke_session,
    verify_session,
)
from broker.app.domain.user import User
from broker.app.services.user_upsert import upsert_user
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def db_session(pg_url: str) -> AsyncIterator[AsyncSession]:
    os.environ["DATABASE_URL"] = pg_url
    from broker.app.core.config import get_settings

    get_settings.cache_clear()
    from broker.app.infra.db import dispose_engine, get_session_factory

    await dispose_engine()
    factory = get_session_factory()
    async with factory() as session:
        yield session
    await dispose_engine()


async def _make_user(session: AsyncSession, external_id: str) -> User:
    user = await upsert_user(
        session,
        UserIdentity(
            external_id=external_id,
            provider="mock",
            display_name=f"User {external_id}",
        ),
    )
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_revoke_all_sessions_only_targets_user(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, "ras-alice-001")
    bob = await _make_user(db_session, "ras-bob-001")

    raws_alice: list[str] = []
    for _ in range(3):
        raw, _ = await issue_session(db_session, alice, ttl_seconds=3600)
        raws_alice.append(raw)
    raw_bob, _ = await issue_session(db_session, bob, ttl_seconds=3600)
    await db_session.commit()

    for raw in raws_alice:
        assert await verify_session(db_session, raw) is not None
    assert await verify_session(db_session, raw_bob) is not None

    revoked = await revoke_all_sessions_for_user(db_session, alice.id)
    await db_session.commit()
    assert revoked == 3

    for raw in raws_alice:
        assert await verify_session(db_session, raw) is None
    assert await verify_session(db_session, raw_bob) is not None


@pytest.mark.asyncio
async def test_revoke_single_session(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "ras-single-001")
    raw1, _ = await issue_session(db_session, user, ttl_seconds=3600)
    raw2, _ = await issue_session(db_session, user, ttl_seconds=3600)
    await db_session.commit()

    revoked = await revoke_session(db_session, raw1)
    await db_session.commit()
    assert revoked == 1

    assert await verify_session(db_session, raw1) is None
    assert await verify_session(db_session, raw2) is not None


@pytest.mark.asyncio
async def test_verify_session_rejects_garbage(db_session: AsyncSession) -> None:
    assert await verify_session(db_session, "") is None
    assert await verify_session(db_session, "garbage-cookie-value") is None
