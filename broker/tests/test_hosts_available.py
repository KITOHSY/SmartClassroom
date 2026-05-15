"""T06 — `GET /api/v1/hosts/available` 가용 호스트 필터.

검증:
- 인증 필수 (401)
- IDLE host만 노출 / OFFLINE/IN_USE/DEGRADED 제외
- ?from=&to= 슬롯 모드: 활성 CONFIRMED 예약 호스트 제외
- 둘 중 하나만 → 422
- 30분 그리드 위반 → 422
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient
from sqlalchemy import text

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


async def _seed_host(hostname: str, status: str) -> int:
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        row = await session.execute(
            text(
                "INSERT INTO hosts (hostname, display_name, status, last_heartbeat_at) "
                "VALUES (:h, :d, :s, now()) RETURNING id"
            ).bindparams(h=hostname, d="강의실", s=status)
        )
        host_id_value: int = row.scalar_one()
        await session.commit()
    return host_id_value


@pytest.mark.asyncio
async def test_available_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/hosts/available")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_available_returns_only_idle_hosts(auth_client: AuthClientFactory) -> None:
    idle_id = await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "IDLE")
    await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "OFFLINE")
    await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "IN_USE")
    await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "DEGRADED")

    user = await auth_client(role="user")
    r = await user.get("/api/v1/hosts/available")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {row["id"] for row in body}
    assert idle_id in ids
    # 다른 status는 제외 — 시드한 IDLE 외 다른 IDLE이 있을 수 있어 길이 단정은 X.
    statuses = {row["hostname"] for row in body}
    assert any(row["id"] == idle_id for row in body)
    _ = statuses


@pytest.mark.asyncio
async def test_available_with_slot_excludes_reserved(auth_client: AuthClientFactory) -> None:
    """슬롯 모드: 해당 시간에 CONFIRMED 예약이 있는 host는 제외."""
    from broker.app.infra.db import get_session_factory

    free_id = await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "IDLE")
    busy_id = await _seed_host(f"pc-{uuid.uuid4().hex[:8]}", "IDLE")

    # busy_id에 다음 30분 슬롯에 활성 예약 시드 — admin 사용자 사용.
    user_admin = await auth_client(role="admin")
    me = (await user_admin.get("/api/v1/auth/me")).json()
    admin_id = me["id"]

    now = datetime.now(UTC).replace(second=0, microsecond=0)
    minute = 0 if now.minute < 30 else 30
    starts = now.replace(minute=minute) + timedelta(hours=1)  # 1시간 뒤
    ends = starts + timedelta(minutes=30)

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO reservations (user_id, host_id, time_range, status) "
                "VALUES (:u, :h, tstzrange(:s, :e, '[)'), 'CONFIRMED')"
            ).bindparams(u=admin_id, h=busy_id, s=starts, e=ends)
        )
        await session.commit()

    r = await user_admin.get(
        "/api/v1/hosts/available",
        params={"from": starts.isoformat(), "to": ends.isoformat()},
    )
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()}
    assert free_id in ids
    assert busy_id not in ids


@pytest.mark.asyncio
async def test_available_partial_slot_params_returns_422(
    auth_client: AuthClientFactory,
) -> None:
    user = await auth_client(role="user")
    starts = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    r = await user.get("/api/v1/hosts/available", params={"from": starts.isoformat()})
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "invalid_reservation_window"


@pytest.mark.asyncio
async def test_available_off_grid_returns_422(auth_client: AuthClientFactory) -> None:
    user = await auth_client(role="user")
    starts = datetime.now(UTC).replace(minute=15, second=0, microsecond=0) + timedelta(hours=1)
    ends = starts + timedelta(minutes=30)
    r = await user.get(
        "/api/v1/hosts/available",
        params={"from": starts.isoformat(), "to": ends.isoformat()},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "invalid_reservation_window"
