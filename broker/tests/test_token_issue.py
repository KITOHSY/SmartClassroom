"""T07 토큰 발급 테스트 — happy / 시간 게이트 / 권한.

CONNECT_TOKEN_GRACE_SECONDS=3600 (conftest._set_test_env) 설정 덕분에
가까운 미래(now+5분)에 시드한 예약은 발급 통과.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _grid_floor(dt: datetime) -> datetime:
    """30분 그리드로 내림."""
    dt = dt.replace(second=0, microsecond=0)
    return dt.replace(minute=0 if dt.minute < 30 else 30)


def _near_future_slot(start_offset_minutes: int = 5, duration_minutes: int = 30) -> tuple[str, str]:
    """now + offset 분에 시작하는 30분 슬롯. grid 정렬 보장."""
    start = _grid_floor(datetime.now(UTC) + timedelta(minutes=start_offset_minutes + 30))
    end = start + timedelta(minutes=duration_minutes)
    return start.isoformat(), end.isoformat()


def _far_future_slot() -> tuple[str, str]:
    """now + 13일 — grace(1시간)보다 멀리, lookahead(14일) 안쪽."""
    start = _grid_floor(datetime.now(UTC) + timedelta(days=13))
    end = start + timedelta(minutes=30)
    return start.isoformat(), end.isoformat()


async def _create_reservation(ac: AsyncClient, host_id: int, starts: str, ends: str) -> int:
    r = await ac.post(
        "/api/v1/reservations",
        json={"host_id": host_id, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _set_host_ip(host_id: int, ip: str) -> None:
    """Host row의 ip_address 직접 INSERT/UPDATE — 발급 응답 검증용."""
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "UPDATE hosts SET ip_address = CAST(:ip AS inet), "
                "sunshine_port = 47984 WHERE id = :id"
            ).bindparams(ip=ip, id=host_id)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_issue_happy_path(auth_client: AuthClientFactory, host: int) -> None:
    """가까운 미래 예약 → 201 + token + host 임베딩, sha256(raw)이 DB jti로 적재."""
    await _set_host_ip(host, "10.1.2.3")
    ac = await auth_client()
    starts, ends = _near_future_slot(5)
    rid = await _create_reservation(ac, host, starts, ends)

    r = await ac.post(f"/api/v1/reservations/{rid}/connect")
    assert r.status_code == 201, r.text
    body = r.json()
    assert "token" in body
    assert isinstance(body["token"], str) and len(body["token"]) >= 32
    assert body["reservation_id"] == rid
    assert body["expires_at"].startswith(ends[:16])

    host_payload = body["host"]
    assert host_payload["id"] == host
    assert host_payload["ip_address"] == "10.1.2.3"
    assert host_payload["sunshine_port"] == 47984
    assert "hostname" in host_payload

    # DB에 sha256(raw)이 jti로 저장되었는지 확인.
    from broker.app.domain.token import Token
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import select

    expected_jti = hashlib.sha256(body["token"].encode("utf-8")).hexdigest()
    factory = get_session_factory()
    async with factory() as session:
        row = await session.scalar(
            select(Token).where(Token.jti == expected_jti, Token.purpose == "connect")
        )
    assert row is not None
    assert row.user_id is not None
    assert row.host_id == host
    assert row.reservation_id == rid
    assert row.consumed_at is None
    assert row.revoked_at is None


@pytest.mark.asyncio
async def test_issue_too_early(auth_client: AuthClientFactory, host: int) -> None:
    """starts_at이 grace(1시간)보다 멀리 있는 예약 → 422 reason=too_early."""
    ac = await auth_client()
    starts, ends = _far_future_slot()
    rid = await _create_reservation(ac, host, starts, ends)

    r = await ac.post(f"/api/v1/reservations/{rid}/connect")
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "invalid_connect_window"
    assert body["detail"]["reason"] == "too_early"


@pytest.mark.asyncio
async def test_issue_after_window(auth_client: AuthClientFactory, host: int) -> None:
    """ends_at이 지난 예약 → 422 reason=expired_window.

    create_reservation이 과거 시작을 막으므로 정상 생성 후 DB 직접 UPDATE로 과거화.
    """
    ac = await auth_client()
    starts, ends = _near_future_slot(5)
    rid = await _create_reservation(ac, host, starts, ends)

    # time_range를 직접 과거로 옮긴다 — overlapping 다른 예약 없으니 EXCLUDE 안전.
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "UPDATE reservations SET time_range = tstzrange("
                "now() - interval '2 hours', "
                "now() - interval '90 minutes', '[)'"
                ") WHERE id = :id"
            ).bindparams(id=rid)
        )
        await session.commit()

    r = await ac.post(f"/api/v1/reservations/{rid}/connect")
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "invalid_connect_window"
    assert body["detail"]["reason"] == "expired_window"


@pytest.mark.asyncio
async def test_issue_canceled_reservation_returns_404(
    auth_client: AuthClientFactory, host: int
) -> None:
    """취소된 예약에 대한 connect → 404 (status='CANCELED' 도달 전 cancel route가 처리).

    cancel route가 reservation을 CANCELED 상태로 만들면, 단건 조회는 200(본인)이지만
    connect 라우트는 reservation_not_active 422를 raise하도록 service가 검증.
    plan: 404 또는 422 reason=reservation_not_active 중 service가 먼저 잡는 쪽 — 후자 채택.
    """
    ac = await auth_client()
    starts, ends = _near_future_slot(5)
    rid = await _create_reservation(ac, host, starts, ends)

    cancel = await ac.delete(f"/api/v1/reservations/{rid}")
    assert cancel.status_code == 204

    r = await ac.post(f"/api/v1/reservations/{rid}/connect")
    # service가 status != CONFIRMED를 검증 → 422 reason=reservation_not_active.
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "invalid_connect_window"
    assert body["detail"]["reason"] == "reservation_not_active"


@pytest.mark.asyncio
async def test_issue_other_user_reservation(auth_client: AuthClientFactory, host: int) -> None:
    """타인 예약에 대한 connect → 404 (존재 노출 방지)."""
    owner = await auth_client()
    intruder = await auth_client()
    starts, ends = _near_future_slot(5)
    rid = await _create_reservation(owner, host, starts, ends)

    r = await intruder.post(f"/api/v1/reservations/{rid}/connect")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_issue_admin_can_issue_for_any_user(
    auth_client: AuthClientFactory, host: int
) -> None:
    """admin은 타인 예약에도 connect 가능."""
    owner = await auth_client()
    admin = await auth_client(role="admin")
    starts, ends = _near_future_slot(5)
    rid = await _create_reservation(owner, host, starts, ends)

    r = await admin.post(f"/api/v1/reservations/{rid}/connect")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reservation_id"] == rid
    assert "token" in body
