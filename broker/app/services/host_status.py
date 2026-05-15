"""T06 — 호스트 상태 머신 (OFFLINE / IDLE / IN_USE / DEGRADED).

전이 평가는 순수 함수(`evaluate_host_status`)로 분리해 단위 테스트가 용이.
DB I/O + audit + SSE publish는 `transition_host` 헬퍼가 담당.

전이 규칙 (priority 순):
1. heartbeat 누락 (없거나 N초 초과) → OFFLINE
2. 활성 예약 + sunshine 실행 → IN_USE
3. 활성 예약 + sunshine 미실행 → DEGRADED (예약자 못 접속하는 실패 신호)
4. 부하 임계 초과 (cpu/mem) → DEGRADED
5. 그 외 → IDLE
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal

from broker.app.core.config import Settings
from broker.app.domain.audit import write_audit
from broker.app.domain.host import Host

if TYPE_CHECKING:
    from broker.app.services.host_events import HostEventBroker
    from sqlalchemy.ext.asyncio import AsyncSession

HostStatus = Literal["OFFLINE", "IDLE", "IN_USE", "DEGRADED"]
HOST_STATES: Final[tuple[HostStatus, ...]] = ("OFFLINE", "IDLE", "IN_USE", "DEGRADED")


def evaluate_host_status(
    *,
    now: datetime,
    last_heartbeat_at: datetime | None,
    has_active_reservation: bool,
    sunshine_running: bool,
    cpu_pct: float | None,
    mem_pct: float | None,
    settings: Settings,
) -> HostStatus:
    """현재 메트릭으로부터 다음 status를 평가. 순수 함수, DB I/O 없음."""
    if last_heartbeat_at is None:
        return "OFFLINE"
    if now - last_heartbeat_at > timedelta(seconds=settings.host_offline_after_seconds):
        return "OFFLINE"

    if has_active_reservation:
        return "IN_USE" if sunshine_running else "DEGRADED"

    if cpu_pct is not None and cpu_pct >= settings.host_degraded_cpu_pct:
        return "DEGRADED"
    if mem_pct is not None and mem_pct >= settings.host_degraded_mem_pct:
        return "DEGRADED"

    return "IDLE"


async def transition_host(
    db: AsyncSession,
    host: Host,
    new_status: HostStatus,
    *,
    reason: str,
    broker: HostEventBroker | None,
    now: datetime,
) -> bool:
    """status가 다르면 UPDATE + audit + SSE publish. 같으면 noop. 변화 여부 반환.

    commit은 호출자(라우터/monitor) 책임. broker가 None이면 SSE publish 생략(테스트 격리용).
    """
    old_status = host.status
    if old_status == new_status:
        return False

    host.status = new_status
    await write_audit(
        db,
        action="host_status_change",
        actor_user_id=None,
        actor_kind="system",
        target_kind="host",
        target_id=host.id,
        detail={"old": old_status, "new": new_status, "reason": reason},
    )
    if broker is not None:
        await broker.publish(
            {
                "event": "host.status",
                "host_id": host.id,
                "hostname": host.hostname,
                "old": old_status,
                "new": new_status,
                "reason": reason,
                "ts": now.isoformat(),
            }
        )
    return True
