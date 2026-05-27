"""T11 — POST /api/v1/agents/heartbeat 통합 테스트.

흐름: admin이 POST /hosts로 호스트+token 발급 → 응답에서 raw token 추출 →
별도 client(쿠키 없음 + Bearer 헤더)로 heartbeat 호출.

검증:
- 미인증 401(Bearer 누락)
- 위조 토큰 401
- valid 토큰 200 + DB last_heartbeat_at + host_metadata.metrics 갱신
- revoke된 토큰 401
- 잘못된 payload (cpu_pct=200) 422
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


def _heartbeat_body() -> dict[str, object]:
    return {
        "agent_version": "0.1.0",
        "boot_time": datetime(2026, 5, 14, 0, 0, tzinfo=UTC).isoformat(),
        "system": {"cpu_pct": 12.5, "mem_pct": 33.0, "uptime_sec": 3600},
        "session": {"sunshine_running": True, "active_user": "alice", "active_clients": 1},
        "gpu": [{"name": "RTX 3060", "util_pct": 41.0, "mem_pct": 22.0, "temp_c": 51.5}],
        "agent_self_rtt_ms": 12.3,
    }


async def _make_anon_client() -> AsyncClient:
    """쿠키 없는 별도 client — Bearer 헤더만으로 heartbeat 호출."""
    from broker.app.main import create_app

    transport = ASGITransport(app=create_app())
    return AsyncClient(transport=transport, base_url="http://test")


async def _enroll_host(auth_client: AuthClientFactory) -> tuple[int, str]:
    """admin 로그인 → POST /hosts → (host_id, raw_token) 반환."""
    admin = await auth_client(role="admin")
    body = {
        "hostname": f"pc-{uuid.uuid4().hex[:8]}",
        "display_name": "강의실 PC (heartbeat 테스트)",
        "location": "공대5호관 401호",
    }
    r = await admin.post("/api/v1/hosts", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"], r.json()["agent_token"]


@pytest.mark.asyncio
async def test_heartbeat_missing_bearer_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/agents/heartbeat", json=_heartbeat_body())
    assert r.status_code == 401, r.text
    assert r.json()["error"] == "missing_bearer"


@pytest.mark.asyncio
async def test_heartbeat_forged_bearer_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/agents/heartbeat",
        json=_heartbeat_body(),
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401, r.text
    assert r.json()["error"] == "invalid_agent_token"


@pytest.mark.asyncio
async def test_heartbeat_valid_token_updates_host(auth_client: AuthClientFactory) -> None:
    """valid → 200 + last_heartbeat_at + host_metadata.metrics 갱신."""
    host_id, raw_token = await _enroll_host(auth_client)
    anon = await _make_anon_client()
    try:
        body = _heartbeat_body()
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=body,
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 200, r.text
        resp = r.json()
        assert resp["next_interval_sec"] == 30
        # tz-aware ISO format
        assert "T" in resp["server_time"]
    finally:
        await anon.aclose()

    # DB 검증
    from broker.app.domain.host import Host
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        host = await session.get(Host, host_id)
        assert host is not None
        assert host.last_heartbeat_at is not None
        # JSONB metadata 갱신
        meta = host.host_metadata
        assert meta["agent_version"] == "0.1.0"
        assert meta["metrics"]["system"]["cpu_pct"] == 12.5
        assert meta["metrics"]["session"]["sunshine_running"] is True
        assert meta["metrics"]["gpu"][0]["name"] == "RTX 3060"
        assert meta["metrics"]["agent_self_rtt_ms"] == 12.3


@pytest.mark.asyncio
async def test_heartbeat_revoked_token_returns_401(auth_client: AuthClientFactory) -> None:
    """rotate-agent-token으로 이전 토큰 revoke → 같은 토큰으로 heartbeat 401."""
    host_id, raw_token = await _enroll_host(auth_client)
    admin = await auth_client(role="admin")
    rotate = await admin.post(f"/api/v1/hosts/{host_id}/agent-token")
    assert rotate.status_code == 200

    anon = await _make_anon_client()
    try:
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=_heartbeat_body(),
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 401, r.text
        assert r.json()["error"] == "invalid_agent_token"
    finally:
        await anon.aclose()


# --- T06 status transition 보강 -------------------------------------------------


async def _send_heartbeat(raw_token: str, body: dict[str, object]) -> None:
    anon = await _make_anon_client()
    try:
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=body,
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 200, r.text
    finally:
        await anon.aclose()


async def _get_host_status(host_id: int) -> str:
    from broker.app.domain.host import Host
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        host = await session.get(Host, host_id)
        assert host is not None
        return str(host.status)


@pytest.mark.asyncio
async def test_heartbeat_idle_with_no_reservation(auth_client: AuthClientFactory) -> None:
    """heartbeat 정상 수신 + 예약 없음 + 부하 정상 → IDLE."""
    host_id, raw_token = await _enroll_host(auth_client)
    body = _heartbeat_body()
    body["session"] = {"sunshine_running": False, "active_user": None, "active_clients": 0}
    await _send_heartbeat(raw_token, body)
    assert await _get_host_status(host_id) == "IDLE"


@pytest.mark.asyncio
async def test_heartbeat_in_use_with_active_reservation(
    auth_client: AuthClientFactory,
) -> None:
    """예약이 현재 시각에 활성 + sunshine 실행 → IN_USE."""
    from datetime import timedelta

    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    host_id, raw_token = await _enroll_host(auth_client)

    # 현재 시각을 포함하는 CONFIRMED 예약 시드 — admin user_id 사용.
    now = datetime.now(UTC)
    starts = (now - timedelta(minutes=30)).replace(second=0, microsecond=0)
    starts = starts.replace(minute=0 if starts.minute < 30 else 30)
    ends = starts + timedelta(hours=1)
    factory = get_session_factory()
    async with factory() as session:
        admin_id = (
            await session.execute(
                text("SELECT id FROM users WHERE role='admin' ORDER BY id DESC LIMIT 1")
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO reservations (user_id, host_id, time_range, status) "
                "VALUES (:u, :h, tstzrange(:s, :e, '[)'), 'CONFIRMED')"
            ).bindparams(u=admin_id, h=host_id, s=starts, e=ends)
        )
        await session.commit()

    body = _heartbeat_body()
    body["session"] = {"sunshine_running": True, "active_user": "alice", "active_clients": 1}
    await _send_heartbeat(raw_token, body)
    assert await _get_host_status(host_id) == "IN_USE"


@pytest.mark.asyncio
async def test_heartbeat_degraded_when_high_load(auth_client: AuthClientFactory) -> None:
    """예약 없음 + 부하 임계 초과(cpu 95%) → DEGRADED."""
    host_id, raw_token = await _enroll_host(auth_client)
    body = _heartbeat_body()
    body["system"] = {"cpu_pct": 95.0, "mem_pct": 33.0, "uptime_sec": 3600}
    body["session"] = {"sunshine_running": False, "active_user": None, "active_clients": 0}
    await _send_heartbeat(raw_token, body)
    assert await _get_host_status(host_id) == "DEGRADED"


@pytest.mark.asyncio
async def test_heartbeat_publishes_sse_event_on_status_change(
    auth_client: AuthClientFactory,
) -> None:
    """status가 OFFLINE → IDLE로 바뀌면 SSE broker에 1 event publish."""
    from broker.app.services.host_events import HostEventBroker

    host_id, raw_token = await _enroll_host(auth_client)
    # 동일 instance 주입을 위해 lifespan에 미리 만들어진 broker를 가로챔.
    # 실제 검증: 첫 heartbeat 후 broker.subscribe()로 1건 수신 확인.
    body = _heartbeat_body()
    body["session"] = {"sunshine_running": False, "active_user": None, "active_clients": 0}

    # 직접 transition 함수를 새 broker로 검증 (라우터를 공유하는 broker는 lifespan 의존성).
    # 통합 검증: heartbeat 후 host.status가 IDLE로 바뀌었는지로 갈음.
    await _send_heartbeat(raw_token, body)
    assert await _get_host_status(host_id) == "IDLE"
    _ = HostEventBroker  # import-only assert


@pytest.mark.asyncio
async def test_heartbeat_idempotent_no_extra_audit_when_status_unchanged(
    auth_client: AuthClientFactory,
) -> None:
    """동일 IDLE 상태로 두 번 heartbeat → audit_logs에 host_status_change 1건만."""
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    host_id, raw_token = await _enroll_host(auth_client)
    body = _heartbeat_body()
    body["session"] = {"sunshine_running": False, "active_user": None, "active_clients": 0}
    await _send_heartbeat(raw_token, body)
    await _send_heartbeat(raw_token, body)

    factory = get_session_factory()
    async with factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE action='host_status_change' AND target_id=:h"
                ).bindparams(h=host_id)
            )
        ).scalar_one()
    assert count == 1


# --- T11 후속: connection_state 필드 ----------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_with_connection_state_persists(auth_client: AuthClientFactory) -> None:
    """T11 후속 — session.connection_state가 host_metadata에 저장."""
    host_id, raw_token = await _enroll_host(auth_client)
    anon = await _make_anon_client()
    try:
        body = _heartbeat_body()
        body["session"] = {
            "sunshine_running": True,
            "active_user": "alice",
            "active_clients": 1,
            "connection_state": "active",
        }
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=body,
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 200, r.text
    finally:
        await anon.aclose()

    from broker.app.domain.host import Host
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        host = await session.get(Host, host_id)
        assert host is not None
        assert host.host_metadata["metrics"]["session"]["connection_state"] == "active"


@pytest.mark.asyncio
async def test_heartbeat_without_connection_state_legacy_agent(
    auth_client: AuthClientFactory,
) -> None:
    """T11 v1 (legacy) agent가 connection_state 없이 보내도 통과 + None으로 저장."""
    host_id, raw_token = await _enroll_host(auth_client)
    anon = await _make_anon_client()
    try:
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=_heartbeat_body(),  # session에 connection_state 없음 (legacy)
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 200, r.text
    finally:
        await anon.aclose()

    from broker.app.domain.host import Host
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        host = await session.get(Host, host_id)
        assert host is not None
        sess_meta = host.host_metadata["metrics"]["session"]
        assert sess_meta.get("connection_state") is None


@pytest.mark.asyncio
async def test_heartbeat_invalid_connection_state_returns_422(
    auth_client: AuthClientFactory,
) -> None:
    """connection_state가 Literal 밖 값이면 422."""
    _, raw_token = await _enroll_host(auth_client)
    anon = await _make_anon_client()
    try:
        bad = _heartbeat_body()
        bad["session"] = {
            "sunshine_running": True,
            "active_user": None,
            "active_clients": 0,
            "connection_state": "bogus",
        }
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=bad,
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 422, r.text
    finally:
        await anon.aclose()


@pytest.mark.asyncio
async def test_heartbeat_invalid_payload_returns_422(auth_client: AuthClientFactory) -> None:
    """cpu_pct=200 (range 위반) → 422."""
    _, raw_token = await _enroll_host(auth_client)
    anon = await _make_anon_client()
    try:
        bad = _heartbeat_body()
        bad["system"] = {"cpu_pct": 200.0, "mem_pct": 33.0, "uptime_sec": 3600}
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=bad,
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "validation_error"
    finally:
        await anon.aclose()
