"""T06 — host_status_monitor `_run_one_tick` 단위 테스트.

freezegun으로 시간 고정 + DB에 stale heartbeat host 시드 → tick 1회 → OFFLINE 전이 확인.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from broker.app.core.config import Settings, get_settings
from broker.app.services.host_events import HostEventBroker
from broker.app.services.host_status_monitor import _run_one_tick
from httpx import AsyncClient


async def _seed_host(hostname: str, status: str, last_heartbeat_at: datetime | None) -> int:
    """직접 INSERT — Host fixture는 status를 강제로 OFFLINE 시드하므로 별도 헬퍼."""
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                "INSERT INTO hosts (hostname, display_name, status, last_heartbeat_at) "
                "VALUES (:h, :d, :s, :lhb) RETURNING id"
            ).bindparams(h=hostname, d="강의실", s=status, lhb=last_heartbeat_at)
        )
        host_id_value: int = result.scalar_one()
        await session.commit()
    return host_id_value


@pytest.mark.asyncio
async def test_monitor_transitions_stale_host_to_offline(client: AsyncClient) -> None:
    """IDLE인데 last_heartbeat_at이 너무 오래된 host → OFFLINE 전이 + count=1."""
    _ = client  # client fixture로 lifespan + DB URL 보장.
    import uuid

    from broker.app.infra.db import get_session_factory

    settings = get_settings()
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=settings.host_offline_after_seconds + 5)
    host_id = await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "IDLE", stale)

    factory = get_session_factory()
    broker = HostEventBroker()
    async with factory() as session:
        count = await _run_one_tick(session, broker, settings, now=now)
    assert count == 1

    async with factory() as session:
        from broker.app.domain.host import Host

        host = await session.get(Host, host_id)
        assert host is not None
        assert host.status == "OFFLINE"


@pytest.mark.asyncio
async def test_monitor_skips_fresh_heartbeat(client: AsyncClient) -> None:
    """IDLE + 최근 heartbeat → 변환 안 됨, count=0."""
    _ = client
    import uuid

    from broker.app.infra.db import get_session_factory

    settings = get_settings()
    now = datetime.now(UTC)
    fresh = now - timedelta(seconds=1)
    host_id = await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "IDLE", fresh)

    factory = get_session_factory()
    async with factory() as session:
        count = await _run_one_tick(session, HostEventBroker(), settings, now=now)
    # 시드된 host 외 다른 stale host가 있을 수도 있어 ==0 단정 어려움 → 시드한 host의 status 검증.
    _ = count

    async with factory() as session:
        from broker.app.domain.host import Host

        host = await session.get(Host, host_id)
        assert host is not None
        assert host.status == "IDLE"


@pytest.mark.asyncio
async def test_monitor_publishes_sse_event_on_offline(client: AsyncClient) -> None:
    """OFFLINE 전이 시 broker에 host.status event publish."""
    _ = client
    import uuid

    from broker.app.infra.db import get_session_factory

    settings = get_settings()
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=settings.host_offline_after_seconds + 60)
    hostname = f"pc-{uuid.uuid4().hex[:8]}"
    await _seed_host(hostname, "IDLE", stale)

    factory = get_session_factory()
    broker = HostEventBroker()

    # subscribe를 task로 띄워 publish 받기.
    received: list[dict[str, object]] = []

    async def _consume() -> None:
        async for ev in broker.subscribe():
            received.append(ev)
            return  # 1건만 받고 종료

    import asyncio

    consumer = asyncio.create_task(_consume())
    # broker가 subscribe 큐를 만들 시간 확보.
    await asyncio.sleep(0.05)

    async with factory() as session:
        await _run_one_tick(session, broker, settings, now=now)

    await asyncio.wait_for(consumer, timeout=2.0)
    matching = [ev for ev in received if ev.get("hostname") == hostname]
    assert matching, f"expected event for {hostname}, got: {received}"
    assert matching[0]["new"] == "OFFLINE"
    assert matching[0]["reason"] == "heartbeat_stale"


@pytest.mark.asyncio
async def test_monitor_treats_null_heartbeat_as_stale(client: AsyncClient) -> None:
    """last_heartbeat_at이 NULL인 새 host도 OFFLINE으로 묶임."""
    _ = client
    import uuid

    from broker.app.infra.db import get_session_factory

    settings = get_settings()
    # status='IDLE' + last_heartbeat_at=NULL 조합이면 stale로 잡힘.
    host_id = await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "IDLE", None)

    factory = get_session_factory()
    async with factory() as session:
        await _run_one_tick(session, HostEventBroker(), settings)

    async with factory() as session:
        from broker.app.domain.host import Host

        host = await session.get(Host, host_id)
        assert host is not None
        assert host.status == "OFFLINE"


@pytest.mark.asyncio
async def test_monitor_idempotent_already_offline(client: AsyncClient) -> None:
    """이미 OFFLINE인 host는 transition 안 됨(no audit row 추가)."""
    _ = client
    import uuid

    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    settings = get_settings()
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=settings.host_offline_after_seconds + 5)
    host_id = await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "OFFLINE", stale)

    factory = get_session_factory()
    async with factory() as session:
        before = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE action='host_status_change' AND target_id=:h"
                ).bindparams(h=host_id)
            )
        ).scalar_one()

    async with factory() as session:
        await _run_one_tick(session, HostEventBroker(), settings, now=now)

    async with factory() as session:
        after = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE action='host_status_change' AND target_id=:h"
                ).bindparams(h=host_id)
            )
        ).scalar_one()
    assert before == after


def test_settings_offline_after_seconds_short_for_tests() -> None:
    """conftest._set_test_env가 짧은 기본값(10s)을 주입했는지."""
    s = Settings()
    assert s.host_offline_after_seconds == 10
    assert s.host_status_monitor_interval_seconds == 2
