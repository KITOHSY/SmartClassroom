"""Heartbeat loop — 30초 주기로 collectors 호출 + broker로 POST.

설계:
- 동기 collectors(psutil/subprocess)는 `asyncio.to_thread`로 비동기 wrapping
- 실패는 로그만 — loop는 계속 (네트워크 일시 단절 시 다음 cycle에 자동 복구)
- `stop_event` 신호 또는 `max_cycles` 도달 시 우아하게 종료
"""

from __future__ import annotations

import asyncio
from typing import Any

from smartclassroom_agent import __version__
from smartclassroom_agent.client import BrokerClient
from smartclassroom_agent.collectors.gpu import collect_gpu
from smartclassroom_agent.collectors.rtt import measure_rtt
from smartclassroom_agent.collectors.session import collect_session
from smartclassroom_agent.collectors.system import boot_time, collect_system
from smartclassroom_agent.logging import get_logger

logger = get_logger(__name__)


async def build_heartbeat_payload(broker_url: str) -> dict[str, Any]:
    """동기 collector는 to_thread, RTT 측정은 직접 await."""
    sys_snap = await asyncio.to_thread(collect_system)
    sess_snap = await asyncio.to_thread(collect_session)
    gpu_snap = await asyncio.to_thread(collect_gpu)
    rtt_ms = await measure_rtt(broker_url)
    return {
        "agent_version": __version__,
        "boot_time": boot_time().isoformat(),
        "system": dict(sys_snap),
        "session": dict(sess_snap),
        "gpu": [dict(g) for g in gpu_snap],
        "agent_self_rtt_ms": rtt_ms,
    }


async def run_heartbeat_loop(
    client: BrokerClient,
    broker_url: str,
    *,
    interval_seconds: float = 30.0,
    stop_event: asyncio.Event | None = None,
    max_cycles: int | None = None,
) -> int:
    """heartbeat 송신 loop. 실행한 cycles 수 반환.

    종료 조건:
    - stop_event.set() 호출
    - max_cycles 도달 (테스트/일회성 용)
    """
    cycles = 0
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            payload = await build_heartbeat_payload(broker_url)
            response = await client.post_heartbeat(payload)
            logger.info(
                "heartbeat ok",
                next_interval=response.get("next_interval_sec"),
                server_time=response.get("server_time"),
            )
        except Exception as exc:
            # 네트워크/HTTP 오류는 로그만 — loop 계속.
            logger.warning("heartbeat failed", error=str(exc), error_type=type(exc).__name__)

        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break

        # interval 동안 stop_event 대기 — 즉시 종료 가능하게.
        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                break
            except TimeoutError:
                continue
        else:
            await asyncio.sleep(interval_seconds)

    return cycles
