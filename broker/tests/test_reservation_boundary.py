"""T05 예약 경계값 — 30분 그리드/과거/lookahead/duration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _round_to_grid() -> datetime:
    n = datetime.now(UTC).replace(second=0, microsecond=0)
    return n.replace(minute=0 if n.minute < 30 else 30)


@pytest.mark.asyncio
async def test_off_grid_starts_at_rejected(auth_client: AuthClientFactory, host: int) -> None:
    a = await auth_client()
    base = _round_to_grid() + timedelta(hours=2)
    # 30분 그리드 위반: 분이 15.
    starts = base.replace(minute=15).isoformat()
    ends = (base + timedelta(hours=1)).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_off_grid_ends_at_rejected(auth_client: AuthClientFactory, host: int) -> None:
    a = await auth_client()
    base = _round_to_grid() + timedelta(hours=2)
    starts = base.isoformat()
    ends = (base + timedelta(minutes=45)).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_naive_datetime_rejected(auth_client: AuthClientFactory, host: int) -> None:
    a = await auth_client()
    base = _round_to_grid() + timedelta(hours=2)
    # tz 정보 제거.
    naive_starts = base.replace(tzinfo=None).isoformat()
    naive_ends = (base + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": naive_starts, "ends_at": naive_ends},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_past_start_rejected(auth_client: AuthClientFactory, host: int) -> None:
    a = await auth_client()
    base = _round_to_grid() - timedelta(hours=2)  # 2시간 전.
    starts = base.isoformat()
    ends = (base + timedelta(hours=1)).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_reservation_window"


@pytest.mark.asyncio
async def test_lookahead_exceeded_rejected(auth_client: AuthClientFactory, host: int) -> None:
    a = await auth_client()
    base = _round_to_grid() + timedelta(days=20)  # default lookahead=14.
    starts = base.isoformat()
    ends = (base + timedelta(hours=1)).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_reservation_window"


@pytest.mark.asyncio
async def test_duration_exceeded_rejected(auth_client: AuthClientFactory, host: int) -> None:
    a = await auth_client()
    base = _round_to_grid() + timedelta(hours=2)
    starts = base.isoformat()
    # default max = 240분. 4시간 30분 → 위반.
    ends = (base + timedelta(minutes=270)).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_reservation_window"


@pytest.mark.asyncio
async def test_starts_after_ends_rejected(auth_client: AuthClientFactory, host: int) -> None:
    a = await auth_client()
    base = _round_to_grid() + timedelta(hours=2)
    starts = (base + timedelta(hours=1)).isoformat()
    ends = base.isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unknown_host_rejected(auth_client: AuthClientFactory) -> None:
    a = await auth_client()
    base = _round_to_grid() + timedelta(hours=2)
    starts = base.isoformat()
    ends = (base + timedelta(hours=1)).isoformat()
    r = await a.post(
        "/api/v1/reservations",
        json={"host_id": 999999, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 422
