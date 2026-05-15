"""T05 예약 CRUD happy path — 생성/단건 조회/리스트/취소."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _future_slot(hours_ahead: int = 1) -> tuple[str, str]:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    # 30분 boundary로 내림.
    now = now.replace(minute=0 if now.minute < 30 else 30)
    start = now + timedelta(hours=hours_ahead)
    end = start + timedelta(minutes=60)
    return start.isoformat(), end.isoformat()


@pytest.mark.asyncio
async def test_create_then_get_then_cancel(auth_client: AuthClientFactory, host: int) -> None:
    ac: AsyncClient = await auth_client()
    starts, ends = _future_slot(2)
    r = await ac.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    rid = body["id"]
    assert body["host_id"] == host
    assert body["status"] == "CONFIRMED"
    assert body["starts_at"].startswith(starts[:16])

    # 단건
    r2 = await ac.get(f"/api/v1/reservations/{rid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == rid

    # 리스트 — 본인 예약만 표시.
    r3 = await ac.get("/api/v1/reservations")
    assert r3.status_code == 200
    ids = [item["id"] for item in r3.json()]
    assert rid in ids

    # 취소.
    r4 = await ac.delete(f"/api/v1/reservations/{rid}")
    assert r4.status_code == 204

    # 취소 멱등 — 다시 호출해도 204.
    r5 = await ac.delete(f"/api/v1/reservations/{rid}")
    assert r5.status_code == 204

    # 단건 조회는 본인이라 여전히 200 (CANCELED 상태).
    r6 = await ac.get(f"/api/v1/reservations/{rid}")
    assert r6.status_code == 200
    assert r6.json()["status"] == "CANCELED"

    # 활성 리스트엔 미포함.
    r7 = await ac.get("/api/v1/reservations")
    assert r7.status_code == 200
    assert rid not in [item["id"] for item in r7.json()]


@pytest.mark.asyncio
async def test_list_with_host_filter(
    auth_client: AuthClientFactory, host: int, other_host: int
) -> None:
    ac: AsyncClient = await auth_client()
    s1, e1 = _future_slot(3)
    s2, e2 = _future_slot(4)

    r1 = await ac.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s1, "ends_at": e1},
    )
    assert r1.status_code == 201
    r2 = await ac.post(
        "/api/v1/reservations",
        json={"host_id": other_host, "starts_at": s2, "ends_at": e2},
    )
    assert r2.status_code == 201

    r3 = await ac.get(f"/api/v1/reservations?host_id={host}")
    assert r3.status_code == 200
    hosts = {item["host_id"] for item in r3.json()}
    assert hosts == {host}


@pytest.mark.asyncio
async def test_audit_log_records_create_and_cancel(
    auth_client: AuthClientFactory, host: int
) -> None:
    ac: AsyncClient = await auth_client()
    starts, ends = _future_slot(5)
    r = await ac.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 201
    rid = r.json()["id"]

    r2 = await ac.delete(f"/api/v1/reservations/{rid}")
    assert r2.status_code == 204

    # audit_logs에 두 액션 모두 적재.
    from broker.app.domain.audit import AuditLog
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as db:
        rows = (
            (
                await db.execute(
                    select(AuditLog.action).where(
                        AuditLog.target_kind == "reservation",
                        AuditLog.target_id == rid,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert "reservation_create" in rows
    assert "reservation_cancel" in rows
