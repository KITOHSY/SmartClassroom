"""T05 권한 분기 — 타인 예약 조회/취소는 404, admin은 통과."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _slot(hours_ahead: int) -> tuple[str, str]:
    n = datetime.now(UTC).replace(second=0, microsecond=0)
    n = n.replace(minute=0 if n.minute < 30 else 30)
    s = n + timedelta(hours=hours_ahead)
    e = s + timedelta(minutes=30)
    return s.isoformat(), e.isoformat()


@pytest.mark.asyncio
async def test_other_user_get_returns_404(
    auth_client: AuthClientFactory, host: int
) -> None:
    owner = await auth_client()
    intruder = await auth_client()
    s, e = _slot(2)
    r1 = await owner.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s, "ends_at": e},
    )
    assert r1.status_code == 201
    rid = r1.json()["id"]

    r2 = await intruder.get(f"/api/v1/reservations/{rid}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_other_user_cancel_returns_404(
    auth_client: AuthClientFactory, host: int
) -> None:
    owner = await auth_client()
    intruder = await auth_client()
    s, e = _slot(3)
    r1 = await owner.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s, "ends_at": e},
    )
    assert r1.status_code == 201
    rid = r1.json()["id"]

    r2 = await intruder.delete(f"/api/v1/reservations/{rid}")
    assert r2.status_code == 404

    # owner 본인은 여전히 취소 가능.
    r3 = await owner.delete(f"/api/v1/reservations/{rid}")
    assert r3.status_code == 204


@pytest.mark.asyncio
async def test_admin_can_get_and_cancel_other_users_reservation(
    auth_client: AuthClientFactory, host: int
) -> None:
    owner = await auth_client()
    admin = await auth_client(role="admin")
    s, e = _slot(4)
    r1 = await owner.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s, "ends_at": e},
    )
    assert r1.status_code == 201
    rid = r1.json()["id"]

    r2 = await admin.get(f"/api/v1/reservations/{rid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == rid

    r3 = await admin.delete(f"/api/v1/reservations/{rid}")
    assert r3.status_code == 204


@pytest.mark.asyncio
async def test_list_only_returns_own_for_normal_user(
    auth_client: AuthClientFactory, host: int
) -> None:
    a = await auth_client()
    b = await auth_client()
    s1, e1 = _slot(5)
    s2, e2 = _slot(6)
    r1 = await a.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s1, "ends_at": e1},
    )
    assert r1.status_code == 201
    r2 = await b.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s2, "ends_at": e2},
    )
    assert r2.status_code == 201
    rid_a = r1.json()["id"]
    rid_b = r2.json()["id"]

    # a의 리스트엔 b의 예약이 보이면 안 됨.
    list_a = await a.get("/api/v1/reservations")
    ids = [item["id"] for item in list_a.json()]
    assert rid_a in ids
    assert rid_b not in ids


@pytest.mark.asyncio
async def test_admin_list_with_user_id_filter(
    auth_client: AuthClientFactory, host: int
) -> None:
    target = await auth_client()
    admin = await auth_client(role="admin")
    s, e = _slot(7)
    r1 = await target.post(
        "/api/v1/reservations",
        json={"host_id": host, "starts_at": s, "ends_at": e},
    )
    assert r1.status_code == 201
    rid = r1.json()["id"]
    target_uid = r1.json()["user_id"]

    r2 = await admin.get(f"/api/v1/reservations?user_id={target_uid}")
    assert r2.status_code == 200
    items = r2.json()
    assert any(item["id"] == rid for item in items)
