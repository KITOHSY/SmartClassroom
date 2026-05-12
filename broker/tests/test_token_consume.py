"""T07 토큰 소비/재발급 테스트.

- 1회 소비 회귀
- 재발급 시 이전 토큰 일괄 revoke + audit token_revoke_previous
- 동시 소비 race-safe (asyncio.gather)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _grid_floor(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    return dt.replace(minute=0 if dt.minute < 30 else 30)


def _near_future_slot(start_offset_minutes: int = 5) -> tuple[str, str]:
    start = _grid_floor(datetime.now(UTC) + timedelta(minutes=start_offset_minutes + 30))
    end = start + timedelta(minutes=30)
    return start.isoformat(), end.isoformat()


async def _create_reservation(ac: AsyncClient, host_id: int) -> int:
    starts, ends = _near_future_slot(5)
    r = await ac.post(
        "/api/v1/reservations",
        json={"host_id": host_id, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


@pytest.mark.asyncio
async def test_verify_consumes_once(auth_client: AuthClientFactory, host: int) -> None:
    """발급 → verify(consume=True) valid=True → 동일 raw 재verify valid=False."""
    owner = await auth_client()
    admin = await auth_client(role="admin")
    rid = await _create_reservation(owner, host)

    issue = await owner.post(f"/api/v1/reservations/{rid}/connect")
    assert issue.status_code == 201
    raw = issue.json()["token"]

    v1 = await admin.post("/api/v1/tokens/verify", json={"token": raw, "consume": True})
    assert v1.status_code == 200
    assert v1.json()["valid"] is True

    v2 = await admin.post("/api/v1/tokens/verify", json={"token": raw, "consume": True})
    assert v2.status_code == 200
    body = v2.json()
    assert body["valid"] is False
    # consumed_at 필드가 채워져 verify_connect_token이 None을 돌려주므로
    # 이 시점은 invalid_or_expired (consumed_at 채워진 row는 select에서 빠짐).
    assert body["reason"] in ("already_consumed", "invalid_or_expired")


@pytest.mark.asyncio
async def test_reissue_revokes_previous(auth_client: AuthClientFactory, host: int) -> None:
    """발급 raw1 → 재 connect → raw2 발급 + audit token_revoke_previous + raw1 invalid."""
    owner = await auth_client()
    admin = await auth_client(role="admin")
    rid = await _create_reservation(owner, host)

    r1 = await owner.post(f"/api/v1/reservations/{rid}/connect")
    assert r1.status_code == 201
    raw1 = r1.json()["token"]

    r2 = await owner.post(f"/api/v1/reservations/{rid}/connect")
    assert r2.status_code == 201
    raw2 = r2.json()["token"]
    assert raw1 != raw2

    # raw1 — revoked → invalid.
    v1 = await admin.post("/api/v1/tokens/verify", json={"token": raw1, "consume": False})
    assert v1.status_code == 200
    assert v1.json()["valid"] is False

    # raw2 — 활성.
    v2 = await admin.post("/api/v1/tokens/verify", json={"token": raw2, "consume": False})
    assert v2.status_code == 200
    assert v2.json()["valid"] is True

    # audit log — token_revoke_previous 1건 (두 번째 발급에서만 발생, 첫 번째는 revoke 대상 없음).
    from broker.app.domain.audit import AuditLog
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        actions = (
            (
                await session.execute(
                    select(AuditLog.action).where(
                        AuditLog.target_kind == "reservation",
                        AuditLog.target_id == rid,
                        AuditLog.action == "token_revoke_previous",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(actions) == 1, f"expected 1 token_revoke_previous, got {len(actions)}"


@pytest.mark.asyncio
async def test_concurrent_verify_only_one_consumes(
    auth_client: AuthClientFactory, host: int
) -> None:
    """asyncio.gather로 동시 verify 2회 → 정확히 1번만 valid=True (DB 직렬화)."""
    owner = await auth_client()
    admin = await auth_client(role="admin")
    rid = await _create_reservation(owner, host)

    issue = await owner.post(f"/api/v1/reservations/{rid}/connect")
    assert issue.status_code == 201
    raw = issue.json()["token"]

    payload = {"token": raw, "consume": True}
    r1, r2 = await asyncio.gather(
        admin.post("/api/v1/tokens/verify", json=payload),
        admin.post("/api/v1/tokens/verify", json=payload),
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    valid_count = sum(1 for r in (r1, r2) if r.json()["valid"])
    assert valid_count == 1, f"expected exactly 1 valid, got {valid_count}: {r1.json()} {r2.json()}"
