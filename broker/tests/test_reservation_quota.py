"""T05 예약 한도 — 동시/일일."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _slot_after(
    reference: datetime, offset_minutes: int, duration_minutes: int = 60
) -> tuple[str, str]:
    start = reference + timedelta(minutes=offset_minutes)
    end = start + timedelta(minutes=duration_minutes)
    return start.isoformat(), end.isoformat()


def _base_now() -> datetime:
    n = datetime.now(UTC).replace(second=0, microsecond=0)
    return n.replace(minute=0 if n.minute < 30 else 30)


@pytest.mark.asyncio
async def test_concurrent_limit_returns_429(
    auth_client: AuthClientFactory, host: int, other_host: int
) -> None:
    """동시 활성 예약 5건 한도 — 6번째 → 429."""
    a = await auth_client()
    base = _base_now() + timedelta(hours=2)

    # 같은 호스트에서 6번 만들면 충돌하므로 host 두 개 번갈아가며 슬롯 분리.
    hosts = [host, other_host]
    successes = 0
    for i in range(5):
        starts, ends = _slot_after(base, offset_minutes=i * 90, duration_minutes=30)
        r = await a.post(
            "/api/v1/reservations",
            json={"host_id": hosts[i % 2], "starts_at": starts, "ends_at": ends},
        )
        assert r.status_code == 201, f"i={i} got {r.status_code} {r.text}"
        successes += 1
    assert successes == 5

    # 6번째 — quota.
    starts, ends = _slot_after(base, offset_minutes=5 * 90, duration_minutes=30)
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": hosts[0], "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["error"] == "reservation_quota_exceeded"


@pytest.mark.asyncio
async def test_daily_hours_limit_returns_429(
    auth_client: AuthClientFactory, host: int, other_host: int
) -> None:
    """하루 최대 8시간 — 누적 9시간째 예약 → 429."""
    a = await auth_client()
    # 같은 날 안에 들어가도록 — 내일 00:30~ 슬롯.
    base_midnight = datetime.now(UTC).replace(hour=0, minute=30, second=0, microsecond=0)
    tomorrow = base_midnight + timedelta(days=1)
    # max_concurrent=5 이내로 동시도 같이 통과해야 하므로, 큰 슬롯 4개(2시간씩 = 8시간) 후 1개 더.
    durations = [120, 120, 120, 120]  # 8시간
    cursor = tomorrow
    hosts = [host, other_host]
    for i, dur in enumerate(durations):
        starts = cursor.isoformat()
        end_dt = cursor + timedelta(minutes=dur)
        ends = end_dt.isoformat()
        r = await a.post(
            "/api/v1/reservations",
            json={"host_id": hosts[i % 2], "starts_at": starts, "ends_at": ends},
        )
        assert r.status_code == 201, f"i={i} {r.status_code} {r.text}"
        cursor = end_dt

    # 9시간째 — 같은 날 안.
    starts = cursor.isoformat()
    ends = (cursor + timedelta(minutes=30)).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": hosts[0], "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 429, r.text
    assert r.json()["error"] == "reservation_quota_exceeded"
    assert r.json()["detail"]["limit"] == "daily_minutes"
