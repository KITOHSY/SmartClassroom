"""T17 즉시 사용 (POST /reservations/instant) 테스트.

즉시 사용은 30분 그리드 시작 제약을 우회(starts_at=now)하되 quota는 그대로 적용한다.
응답은 예약 생성 + connect 토큰을 한 번에 담은 ConnectTokenResponse.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


async def _set_host_status(host_id: int, status: str) -> None:
    """Host row의 status 직접 UPDATE — 기본 시드는 OFFLINE이라 IDLE 강제용."""
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("UPDATE hosts SET status = :s WHERE id = :id").bindparams(s=status, id=host_id)
        )
        await session.commit()


async def _reservation_bounds(reservation_id: int) -> tuple[datetime, datetime]:
    """reservations.time_range의 [lower, upper)를 tz-aware datetime으로 반환."""
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT lower(time_range), upper(time_range) FROM reservations WHERE id = :id"
                ).bindparams(id=reservation_id)
            )
        ).one()
    lo, hi = row[0], row[1]
    if lo.tzinfo is None:
        lo = lo.replace(tzinfo=UTC)
    if hi.tzinfo is None:
        hi = hi.replace(tzinfo=UTC)
    return lo, hi


def _grid_floor(dt: datetime) -> datetime:
    """30분 그리드로 내림."""
    dt = dt.replace(second=0, microsecond=0)
    return dt.replace(minute=0 if dt.minute < 30 else 30)


async def _seed_future_reservation(ac: AsyncClient, host_id: int, offset_hours: int) -> None:
    """now+1일+offset시간에 시작하는 30분 예약 1건 생성 (concurrent quota 소진용)."""
    start = _grid_floor(datetime.now(UTC) + timedelta(days=1, hours=offset_hours))
    end = start + timedelta(minutes=30)
    r = await ac.post(
        "/api/v1/reservations",
        json={
            "host_id": host_id,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_instant_happy_path(auth_client: AuthClientFactory, host: int) -> None:
    """IDLE 호스트 즉시 사용 → 201 + token + host, 윈도우 산정·audit 확인."""
    await _set_host_status(host, "IDLE")
    ac = await auth_client()

    before = datetime.now(UTC)
    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host})
    after = datetime.now(UTC)
    assert r.status_code == 201, r.text
    body = r.json()

    assert isinstance(body["token"], str) and len(body["token"]) >= 32
    rid = int(body["reservation_id"])
    assert body["host"]["id"] == host

    lo, hi = await _reservation_bounds(rid)
    # starts_at = now (그리드 미정렬) — 호출 직전~직후 사이.
    assert before - timedelta(seconds=2) <= lo <= after + timedelta(seconds=2)
    # ends_at = 30분 그리드 정렬.
    assert hi.minute in (0, 30) and hi.second == 0 and hi.microsecond == 0
    # 윈도우 길이 2.5h ~ 3h.
    assert timedelta(hours=2, minutes=30) <= (hi - lo) <= timedelta(hours=3)
    # expires_at == ends_at.
    assert body["expires_at"].startswith(hi.isoformat()[:16])

    # audit — reservation_create(instant=true) + token_issue(client=instant_use).
    from broker.app.domain.audit import AuditLog
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        rc = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "reservation_create",
                AuditLog.target_kind == "reservation",
                AuditLog.target_id == rid,
            )
        )
        token_audits = (
            (await session.execute(select(AuditLog).where(AuditLog.action == "token_issue")))
            .scalars()
            .all()
        )
    assert rc is not None
    assert rc.detail.get("instant") is True
    ti = next((a for a in token_audits if a.detail.get("reservation_id") == rid), None)
    assert ti is not None
    assert ti.detail.get("client") == "instant_use"


@pytest.mark.asyncio
async def test_instant_marks_host_in_use(auth_client: AuthClientFactory, host: int) -> None:
    """즉시 사용 성공 → 호스트 status가 IDLE에서 IN_USE로 전이된다 (T21 피드백)."""
    await _set_host_status(host, "IDLE")
    ac = await auth_client()

    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host})
    assert r.status_code == 201, r.text

    from broker.app.domain.host import Host
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        h = await session.get(Host, host)
    assert h is not None
    assert h.status == "IN_USE"


@pytest.mark.asyncio
async def test_cancel_reverts_host_to_idle(auth_client: AuthClientFactory, host: int) -> None:
    """즉시 사용으로 IN_USE가 된 호스트는 예약 취소 시 IDLE로 복귀한다 (T21 후속)."""
    await _set_host_status(host, "IDLE")
    ac = await auth_client()

    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host})
    assert r.status_code == 201, r.text
    rid = int(r.json()["reservation_id"])

    from broker.app.domain.host import Host
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        h = await session.get(Host, host)
        assert h is not None and h.status == "IN_USE"

    d = await ac.delete(f"/api/v1/reservations/{rid}")
    assert d.status_code == 204, d.text

    async with factory() as session:
        h = await session.get(Host, host)
    assert h is not None
    assert h.status == "IDLE"


@pytest.mark.asyncio
async def test_instant_quota_exceeded(
    auth_client: AuthClientFactory, host: int, other_host: int
) -> None:
    """동시 활성 예약 5건(quota)이 차 있으면 즉시 사용 → 429."""
    await _set_host_status(host, "IDLE")
    ac = await auth_client()
    for i in range(5):
        await _seed_future_reservation(ac, other_host, offset_hours=i)

    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host})
    assert r.status_code == 429, r.text


@pytest.mark.asyncio
async def test_instant_host_not_idle(auth_client: AuthClientFactory, host: int) -> None:
    """호스트가 IDLE이 아니면 409 host_not_available (host fixture 기본 status=OFFLINE)."""
    ac = await auth_client()
    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host})
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "host_not_available"


@pytest.mark.asyncio
async def test_instant_conflict(auth_client: AuthClientFactory, host: int) -> None:
    """호스트에 now를 덮는 활성 예약이 이미 있으면 즉시 사용 → 409 reservation_conflict."""
    await _set_host_status(host, "IDLE")
    ac = await auth_client()

    # now를 덮는 CONFIRMED 예약을 raw INSERT — T05 starts_at>=now 정책 우회(의도된 테스트 hack).
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO reservations (user_id, host_id, time_range, status) "
                "SELECT id, :hid, "
                "tstzrange(now(), now() + interval '30 minutes', '[)'), 'CONFIRMED' "
                "FROM users LIMIT 1"
            ).bindparams(hid=host)
        )
        await session.commit()

    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host})
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "reservation_conflict"


@pytest.mark.asyncio
async def test_instant_unknown_host_returns_422(auth_client: AuthClientFactory, host: int) -> None:
    """존재하지 않는 host_id → 422 (HostNotFoundError → InvalidReservationWindowError)."""
    ac = await auth_client()
    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host + 999_999})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_instant_window_capped_by_next_reservation(
    auth_client: AuthClientFactory, host: int
) -> None:
    """다음 예약이 2.5h 안에 있으면 즉시 사용 윈도우가 그 시작 시각에서 잘린다."""
    await _set_host_status(host, "IDLE")
    ac = await auth_client()

    # 1시간 뒤 시작하는 CONFIRMED 예약을 raw INSERT.
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        row = await session.execute(
            text(
                "INSERT INTO reservations (user_id, host_id, time_range, status) "
                "SELECT id, :hid, "
                "tstzrange(now() + interval '1 hour', now() + interval '2 hours', '[)'), "
                "'CONFIRMED' FROM users LIMIT 1 "
                "RETURNING lower(time_range)"
            ).bindparams(hid=host)
        )
        next_start: datetime = row.scalar_one()
        await session.commit()
    if next_start.tzinfo is None:
        next_start = next_start.replace(tzinfo=UTC)

    r = await ac.post("/api/v1/reservations/instant", json={"host_id": host})
    assert r.status_code == 201, r.text
    rid = int(r.json()["reservation_id"])

    lo, hi = await _reservation_bounds(rid)
    # 윈도우가 다음 예약 시작(≈now+1h)에서 잘렸다 — 2.5h가 아니라 약 1h.
    assert (hi - lo) <= timedelta(hours=1, minutes=1)
    # ends_at == 다음 예약 시작 시각 (반열림이라 경계 접촉, 충돌 없음).
    assert abs((hi - next_start).total_seconds()) < 2
