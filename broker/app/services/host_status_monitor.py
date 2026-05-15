"""T06 — stale heartbeat → OFFLINE detector background task.

`run_monitor_loop`은 lifespan에서 `asyncio.create_task`로 기동된다.
1 tick = `host_status_monitor_interval_seconds`. 매 tick마다 SELECT로
"OFFLINE이 아닌데 last_heartbeat_at이 너무 오래된" host들을 OFFLINE으로 전이.

테스트는 `_run_one_tick`을 직접 호출해 freezegun으로 시간을 고정한 채 검증.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from broker.app.core.config import Settings
from broker.app.domain.host import Host
from broker.app.infra.db import get_session_factory
from broker.app.services.host_status import transition_host
from sqlalchemy import select

if TYPE_CHECKING:
    from broker.app.services.host_events import HostEventBroker
    from sqlalchemy.ext.asyncio import AsyncSession

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def _run_one_tick(
    db: AsyncSession,
    broker: HostEventBroker | None,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    """1회 stale 체크 + OFFLINE 전이. 변환된 host 수 반환."""
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(seconds=settings.host_offline_after_seconds)

    stmt = select(Host).where(
        Host.status != "OFFLINE",
        # NULL last_heartbeat_at도 OFFLINE 후보 — 한 번도 보고 안 한 호스트.
        (Host.last_heartbeat_at.is_(None)) | (Host.last_heartbeat_at < cutoff),
    )
    rows = list((await db.execute(stmt)).scalars().all())

    transitioned = 0
    for host in rows:
        changed = await transition_host(
            db,
            host,
            "OFFLINE",
            reason="heartbeat_stale",
            broker=broker,
            now=current,
        )
        if changed:
            transitioned += 1

    if transitioned:
        await db.commit()

    return transitioned


async def run_monitor_loop(
    broker: HostEventBroker,
    stop_event: asyncio.Event,
    settings: Settings,
) -> None:
    """lifespan에서 task로 기동. stop_event.set() 까지 주기적 tick."""
    interval = settings.host_status_monitor_interval_seconds
    logger.info("host_status_monitor.start", interval_seconds=interval)
    factory = get_session_factory()
    while not stop_event.is_set():
        try:
            async with factory() as session:
                count = await _run_one_tick(session, broker, settings)
            if count:
                logger.info("host_status_monitor.tick", offline_transitions=count)
        except Exception as exc:
            logger.warning("host_status_monitor.tick_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue
    logger.info("host_status_monitor.stop")
