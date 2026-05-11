"""T05 예약 충돌 — 동일 슬롯 → 409. 취소 후 재예약 → 201."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _slot(hours_ahead: int, duration_minutes: int = 60) -> tuple[str, str]:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    now = now.replace(minute=0 if now.minute < 30 else 30)
    start = now + timedelta(hours=hours_ahead)
    end = start + timedelta(minutes=duration_minutes)
    return start.isoformat(), end.isoformat()


@pytest.mark.asyncio
async def test_exact_slot_conflict_returns_409(
    auth_client: AuthClientFactory, host: int
) -> None:
    a = await auth_client()
    b = await auth_client()
    starts, ends = _slot(2)

    r1 = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r1.status_code == 201

    r2 = await b.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r2.status_code == 409
    body = r2.json()
    assert body["error"] == "reservation_conflict"


@pytest.mark.asyncio
async def test_overlap_partial_returns_409(
    auth_client: AuthClientFactory, host: int
) -> None:
    a = await auth_client()
    b = await auth_client()
    s1, e1 = _slot(3, duration_minutes=60)  # 예: 10:00-11:00
    # 30분 겹치는 슬롯
    start1 = datetime.fromisoformat(s1)
    overlap_start = (start1 + timedelta(minutes=30)).isoformat()
    overlap_end = (start1 + timedelta(minutes=90)).isoformat()

    r1 = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s1, "ends_at": e1},
    )
    assert r1.status_code == 201, r1.text

    r2 = await b.post(
        "/api/v1/reservations",
        json={
            "host_id": host,
            "starts_at": overlap_start,
            "ends_at": overlap_end,
        },
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_rebook_after_cancel_succeeds(
    auth_client: AuthClientFactory, host: int
) -> None:
    a = await auth_client()
    b = await auth_client()
    starts, ends = _slot(4)

    r1 = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r1.status_code == 201
    rid = r1.json()["id"]

    # a가 취소.
    r2 = await a.delete(f"/api/v1/reservations/{rid}")
    assert r2.status_code == 204

    # b가 같은 슬롯 재예약 — 성공해야 함 (EXCLUDE 제약이 CANCELED 자동 제외).
    r3 = await b.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r3.status_code == 201, r3.text


@pytest.mark.asyncio
async def test_adjacent_slot_does_not_conflict(
    auth_client: AuthClientFactory, host: int
) -> None:
    """[)' 반-개구간 → 끝나는 시각과 시작 시각이 같으면 겹치지 않아야 함."""
    a = await auth_client()
    b = await auth_client()
    s1, e1 = _slot(5, duration_minutes=60)
    e1_dt = datetime.fromisoformat(e1)
    s2 = e1_dt.isoformat()
    e2 = (e1_dt + timedelta(minutes=30)).isoformat()

    r1 = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s1, "ends_at": e1},
    )
    assert r1.status_code == 201, r1.text

    r2 = await b.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s2, "ends_at": e2},
    )
    assert r2.status_code == 201, r2.text
