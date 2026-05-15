"""T11 — 에이전트 ingest 라우터.

POST /agents/heartbeat — 호스트 에이전트가 30초 주기로 호출.
- 인증: Bearer agent token (`get_agent_host` 의존성).
- DB 업데이트: hosts.last_heartbeat_at = now, hosts.host_metadata.metrics 갱신.
- v1은 audit log 작성 안 함 — 30초 주기 폭증 회피. T06 본구현 시 sampling으로 도입.
- 상태 머신(OFFLINE/IDLE/IN_USE/DEGRADED) 전이 룰은 T06 본구현이 흡수 — 본 라우터는 raw만 적재.
"""

from __future__ import annotations

from datetime import UTC, datetime

from broker.app.api.deps import get_agent_host, get_db
from broker.app.api.schemas.agent import HeartbeatRequest, HeartbeatResponse
from broker.app.domain.host import Host
from broker.app.domain.token import Token
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat_endpoint(
    payload: HeartbeatRequest,
    agent: tuple[Host, Token] = Depends(get_agent_host),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatResponse:
    """heartbeat 1회 수신."""
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

    await db.commit()
    return HeartbeatResponse(next_interval_sec=30, server_time=now)
