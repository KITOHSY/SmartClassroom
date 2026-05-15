"""heartbeat loop — 짧은 interval + max_cycles로 1주기 동작 확인.

실제 collectors(psutil/subprocess)는 그대로 실행 — 환경 의존성 없는 부분만 검증.
RTT/heartbeat HTTP는 pytest-httpx로 mock.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


@pytest.mark.asyncio
async def test_loop_runs_max_cycles_and_sends_payload(httpx_mock: HTTPXMock) -> None:
    from smartclassroom_agent.client import BrokerClient
    from smartclassroom_agent.heartbeat import run_heartbeat_loop

    # 2 cycle x (healthz + heartbeat) = 총 4 응답 등록
    for _ in range(2):
        httpx_mock.add_response(url="http://broker.test/healthz", json={"status": "ok"})
        httpx_mock.add_response(
            url="http://broker.test/api/v1/agents/heartbeat",
            method="POST",
            json={"next_interval_sec": 30, "server_time": "2026-05-14T00:00:00+00:00"},
        )

    async with BrokerClient("http://broker.test", "tok") as client:
        cycles = await run_heartbeat_loop(
            client,
            "http://broker.test",
            interval_seconds=0.01,
            max_cycles=2,
        )
    assert cycles == 2

    heartbeats = [r for r in httpx_mock.get_requests() if "heartbeat" in str(r.url)]
    assert len(heartbeats) == 2


@pytest.mark.asyncio
async def test_loop_exits_on_stop_event(httpx_mock: HTTPXMock) -> None:
    from smartclassroom_agent.client import BrokerClient
    from smartclassroom_agent.heartbeat import run_heartbeat_loop

    httpx_mock.add_response(url="http://broker.test/healthz", json={"status": "ok"})
    httpx_mock.add_response(
        url="http://broker.test/api/v1/agents/heartbeat",
        method="POST",
        json={"next_interval_sec": 30, "server_time": "2026-05-14T00:00:00+00:00"},
    )

    stop_event = asyncio.Event()

    async def _signal_stop() -> None:
        await asyncio.sleep(0.05)
        stop_event.set()

    async with BrokerClient("http://broker.test", "tok") as client:
        signaller = asyncio.create_task(_signal_stop())
        cycles = await run_heartbeat_loop(
            client,
            "http://broker.test",
            interval_seconds=10.0,  # 길게 — stop_event 신호로 빠져나옴
            stop_event=stop_event,
            max_cycles=10,
        )
        await signaller
    # 1주기 이후 wait_for(stop_event) 가 set되며 break — 정확히 1 cycle.
    assert cycles == 1


@pytest.mark.asyncio
async def test_loop_continues_on_heartbeat_failure(httpx_mock: HTTPXMock) -> None:
    """heartbeat 401 등 실패해도 다음 cycle 진행."""
    from smartclassroom_agent.client import BrokerClient
    from smartclassroom_agent.heartbeat import run_heartbeat_loop

    httpx_mock.add_response(url="http://broker.test/healthz", json={"status": "ok"})
    httpx_mock.add_response(
        url="http://broker.test/api/v1/agents/heartbeat",
        method="POST",
        status_code=401,
        json={"error": "invalid_agent_token"},
    )
    httpx_mock.add_response(url="http://broker.test/healthz", json={"status": "ok"})
    httpx_mock.add_response(
        url="http://broker.test/api/v1/agents/heartbeat",
        method="POST",
        json={"next_interval_sec": 30, "server_time": "..."},
    )

    async with BrokerClient("http://broker.test", "tok") as client:
        cycles = await run_heartbeat_loop(
            client,
            "http://broker.test",
            interval_seconds=0.01,
            max_cycles=2,
        )
    assert cycles == 2
