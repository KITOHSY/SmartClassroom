"""T06 — Prometheus gauge 노출 검증.

heartbeat 후 `/metrics` 엔드포인트에 `broker_host_cpu_percent{hostname=...}`이 보여야 함.
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
        "system": {"cpu_pct": 42.0, "mem_pct": 51.5, "uptime_sec": 100},
        "session": {"sunshine_running": False, "active_user": None, "active_clients": 0},
        "gpu": [{"name": "RTX 3060", "util_pct": 33.0, "mem_pct": 22.0}],
        "agent_self_rtt_ms": 10.0,
    }


async def _make_anon_client() -> AsyncClient:
    from broker.app.main import create_app

    transport = ASGITransport(app=create_app())
    return AsyncClient(transport=transport, base_url="http://test")


async def _enroll_host(auth_client: AuthClientFactory, hostname: str) -> tuple[int, str]:
    admin = await auth_client(role="admin")
    body = {
        "hostname": hostname,
        "display_name": "metrics test host",
        "location": "lab",
    }
    r = await admin.post("/api/v1/hosts", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"], r.json()["agent_token"]


@pytest.mark.asyncio
async def test_heartbeat_exposes_host_gauges_in_metrics(
    auth_client: AuthClientFactory, client: AsyncClient
) -> None:
    hostname = f"pc-metrics-{uuid.uuid4().hex[:6]}"
    _, raw_token = await _enroll_host(auth_client, hostname)

    anon = await _make_anon_client()
    try:
        r = await anon.post(
            "/api/v1/agents/heartbeat",
            json=_heartbeat_body(),
            headers={"Authorization": f"Bearer {raw_token}"},
        )
        assert r.status_code == 200, r.text
    finally:
        await anon.aclose()

    metrics_resp = await client.get("/metrics")
    assert metrics_resp.status_code == 200
    text = metrics_resp.text
    assert f'broker_host_cpu_percent{{hostname="{hostname}"}} 42.0' in text
    assert f'broker_host_mem_percent{{hostname="{hostname}"}} 51.5' in text
    assert f'broker_host_gpu_percent{{hostname="{hostname}"}} 33.0' in text
    # 상태 indicator — IDLE 라벨이 1, 나머지 0.
    assert f'broker_host_status_info{{hostname="{hostname}",status="IDLE"}} 1.0' in text
    assert f'broker_host_status_info{{hostname="{hostname}",status="OFFLINE"}} 0.0' in text
