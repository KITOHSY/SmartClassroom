"""시스템 메트릭 수집 — psutil 의존.

함수는 동기. heartbeat loop가 asyncio.to_thread로 래핑.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import psutil


class SystemSnapshot(TypedDict):
    cpu_pct: float
    mem_pct: float
    uptime_sec: int
    load_avg: list[float] | None


def boot_time() -> datetime:
    """tz-aware UTC boot time."""
    return datetime.fromtimestamp(psutil.boot_time(), tz=UTC)


def _load_avg() -> list[float] | None:
    """Linux/macOS만 — Windows는 None."""
    getloadavg = getattr(psutil, "getloadavg", None)
    if getloadavg is None:
        return None
    try:
        return [round(x, 2) for x in getloadavg()]
    except OSError:
        return None


def collect_system() -> SystemSnapshot:
    """현재 시스템 부하 스냅샷.

    `cpu_percent(interval=None)`은 직전 호출 이후 평균 — 첫 호출은 0.0이 정상.
    heartbeat loop 첫 주기는 워밍업으로 무시하거나 prime 호출을 별도로 둘 수 있음.
    """
    uptime = int(datetime.now(UTC).timestamp() - psutil.boot_time())
    return SystemSnapshot(
        cpu_pct=float(psutil.cpu_percent(interval=None)),
        mem_pct=float(psutil.virtual_memory().percent),
        uptime_sec=uptime,
        load_avg=_load_avg(),
    )
