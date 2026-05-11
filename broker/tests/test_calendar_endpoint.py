"""T05 캘린더 매트릭스 — 구조 + CANCELED 행 제외 + 마스킹."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _next_day_window() -> tuple[datetime, datetime]:
    """내일 09:00 ~ 12:00 (3시간) 윈도우."""
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now + timedelta(days=1, hours=9)
    end = start + timedelta(hours=3)
    return start, end


@pytest.mark.asyncio
async def test_calendar_returns_slots_for_window(
    auth_client: AuthClientFactory, host: int
) -> None:
    a = await auth_client()
    win_from, win_to = _next_day_window()

    # 슬롯 1개 예약: 10:00-10:30 = 1개 슬롯.
    res_start = win_from + timedelta(hours=1)
    res_end = res_start + timedelta(minutes=30)
    r = await a.post(
        "/api/v1/reservations",
        json={
            "host_id": host,
            "starts_at": res_start.isoformat(),
            "ends_at": res_end.isoformat(),
        },
    )
    assert r.status_code == 201, r.text

    r2 = await a.get(
        "/api/v1/reservations/calendar",
        params={
            "from": win_from.isoformat(),
            "to": win_to.isoformat(),
            "host_id": host,
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["slot_minutes"] == 30
    # 3시간 / 30분 = 6 슬롯, host 1개 → 6.
    assert len(body["slots"]) == 6
    occupied = [s for s in body["slots"] if s["status"] == "OCCUPIED"]
    assert len(occupied) == 1
    assert occupied[0]["host_id"] == host
    # 본인 예약이므로 user_id 노출.
    assert occupied[0]["user_id"] is not None


@pytest.mark.asyncio
async def test_calendar_excludes_canceled(
    auth_client: AuthClientFactory, host: int
) -> None:
    a = await auth_client()
    win_from, win_to = _next_day_window()
    res_start = win_from
    res_end = res_start + timedelta(minutes=30)
    r = await a.post(
        "/api/v1/reservations",
        json={
            "host_id": host,
            "starts_at": res_start.isoformat(),
            "ends_at": res_end.isoformat(),
        },
    )
    assert r.status_code == 201
    rid = r.json()["id"]

    # 매트릭스 확인 — 1개 OCCUPIED.
    r1 = await a.get(
        "/api/v1/reservations/calendar",
        params={
            "from": win_from.isoformat(),
            "to": win_to.isoformat(),
            "host_id": host,
        },
    )
    assert any(s["status"] == "OCCUPIED" for s in r1.json()["slots"])

    # 취소 후엔 전부 OPEN.
    await a.delete(f"/api/v1/reservations/{rid}")
    r2 = await a.get(
        "/api/v1/reservations/calendar",
        params={
            "from": win_from.isoformat(),
            "to": win_to.isoformat(),
            "host_id": host,
        },
    )
    assert all(s["status"] == "OPEN" for s in r2.json()["slots"])


@pytest.mark.asyncio
async def test_calendar_masks_other_users(
    auth_client: AuthClientFactory, host: int
) -> None:
    owner = await auth_client()
    viewer = await auth_client()
    win_from, win_to = _next_day_window()
    res_start = win_from + timedelta(hours=2)
    res_end = res_start + timedelta(minutes=30)
    r = await owner.post(
        "/api/v1/reservations",
        json={
            "host_id": host,
            "starts_at": res_start.isoformat(),
            "ends_at": res_end.isoformat(),
        },
    )
    assert r.status_code == 201

    r2 = await viewer.get(
        "/api/v1/reservations/calendar",
        params={
            "from": win_from.isoformat(),
            "to": win_to.isoformat(),
            "host_id": host,
        },
    )
    assert r2.status_code == 200
    occupied = [s for s in r2.json()["slots"] if s["status"] == "OCCUPIED"]
    assert len(occupied) == 1
    # 타인 예약이므로 user_id는 마스킹 (None).
    assert occupied[0]["user_id"] is None
    # reservation_id는 노출 OK (PK는 단순 정수, 사용자 식별성 없음).


@pytest.mark.asyncio
async def test_calendar_window_validation(
    auth_client: AuthClientFactory, host: int
) -> None:
    a = await auth_client()
    win_from, win_to = _next_day_window()
    # off-grid from.
    bad_from = win_from.replace(minute=15)
    r = await a.get(
        "/api/v1/reservations/calendar",
        params={
            "from": bad_from.isoformat(),
            "to": win_to.isoformat(),
            "host_id": host,
        },
    )
    assert r.status_code == 422
