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
