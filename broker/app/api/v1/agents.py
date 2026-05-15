"""T11 + T06 — 에이전트 ingest 라우터.

POST /agents/heartbeat — 호스트 에이전트가 30초 주기로 호출.
- 인증: Bearer agent token (`get_agent_host` 의존성).
- T11: hosts.last_heartbeat_at + host_metadata.metrics(latest) 갱신.
- T06: 활성 예약 + sunshine + 부하를 평가해 status 전이(IDLE/IN_USE/DEGRADED).
  - 변화 시 audit + SSE publish.
  - OFFLINE 전이는 본 라우터가 책임 안 짐(방금 heartbeat 받았으므로) — monitor가 stale 검사.
- audit는 status 변화에만 — 30초 주기 폭증 회피.
"""

from __future__ import annotations

from datetime import UTC, datetime

from broker.app.api.deps import get_agent_host, get_db, get_host_event_broker
from broker.app.api.schemas.agent import HeartbeatRequest, HeartbeatResponse
from broker.app.core.config import get_settings
from broker.app.core.metrics import (
    HOST_CPU_PERCENT,
    HOST_GPU_PERCENT,
    HOST_MEM_PERCENT,
    set_host_status_indicator,
)
from broker.app.domain.host import Host
from broker.app.domain.token import Token
from broker.app.services.host_events import HostEventBroker
from broker.app.services.host_status import evaluate_host_status, transition_host
from broker.app.services.reservation import get_active_reservation_for_host
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat_endpoint(
    payload: HeartbeatRequest,
    agent: tuple[Host, Token] = Depends(get_agent_host),
    db: AsyncSession = Depends(get_db),
    broker: HostEventBroker = Depends(get_host_event_broker),
) -> HeartbeatResponse:
    """heartbeat 1회 수신 + 상태 머신 평가."""
    host, _token = agent
    now = datetime.now(UTC)
    host.last_heartbeat_at = now

    # JSONB 변경은 새 dict 할당으로 — mutable in-place는 SQLAlchemy 변경 감지 누락 가능.
    metadata = dict(host.host_metadata or {})
    metadata["agent_version"] = payload.agent_version
    metadata["boot_time"] = payload.boot_time.isoformat()
    metadata["metrics"] = {
        "system": payload.system.model_dump(),
        "session": payload.session.model_dump(),
        "gpu": [g.model_dump() for g in (payload.gpu or [])],
        "agent_self_rtt_ms": payload.agent_self_rtt_ms,
    }
    host.host_metadata = metadata

    # T06 — status 전이 평가.
    settings = get_settings()
    active_reservation = await get_active_reservation_for_host(db, host.id, at_time=now)
    gpu_max = max((g.util_pct for g in (payload.gpu or [])), default=0.0)
    new_status = evaluate_host_status(
        now=now,
        last_heartbeat_at=now,
        has_active_reservation=active_reservation is not None,
        sunshine_running=payload.session.sunshine_running,
        cpu_pct=payload.system.cpu_pct,
        mem_pct=payload.system.mem_pct,
        settings=settings,
    )
    await transition_host(db, host, new_status, reason="heartbeat", broker=broker, now=now)

    # Prometheus gauge — heartbeat 마지막 값.
    HOST_CPU_PERCENT.labels(hostname=host.hostname).set(payload.system.cpu_pct)
    HOST_MEM_PERCENT.labels(hostname=host.hostname).set(payload.system.mem_pct)
    if payload.gpu:
        HOST_GPU_PERCENT.labels(hostname=host.hostname).set(gpu_max)
    set_host_status_indicator(host.hostname, new_status)

    await db.commit()
    return HeartbeatResponse(next_interval_sec=30, server_time=now)
