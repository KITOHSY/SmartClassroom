"""BrokerClient — Bearer 헤더 자동 첨부 + JSON 직렬화 검증."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


@pytest.mark.asyncio
async def test_post_heartbeat_attaches_bearer_header(httpx_mock: HTTPXMock) -> None:
    from smartclassroom_agent.client import BrokerClient

    httpx_mock.add_response(
        url="http://broker.test/api/v1/agents/heartbeat",
        method="POST",
        json={"next_interval_sec": 30, "server_time": "2026-05-14T00:00:00+00:00"},
    )
    async with BrokerClient("http://broker.test", "secret-token") as client:
        result = await client.post_heartbeat({"agent_version": "0.1.0"})

    assert result["next_interval_sec"] == 30

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    req = requests[0]
    assert req.headers["authorization"] == "Bearer secret-token"
    body = json.loads(req.content)
    assert body["agent_version"] == "0.1.0"


@pytest.mark.asyncio
async def test_post_heartbeat_raises_on_401(httpx_mock: HTTPXMock) -> None:
    from smartclassroom_agent.client import BrokerClient

    httpx_mock.add_response(
        url="http://broker.test/api/v1/agents/heartbeat",
        method="POST",
        status_code=401,
        json={"error": "invalid_agent_token", "message": "..."},
    )
    async with BrokerClient("http://broker.test", "bad") as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.post_heartbeat({"agent_version": "0.1.0"})
