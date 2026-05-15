"""T06 — `GET /api/v1/events/hosts` SSE 채널.

검증:
- 인증 필수 (401)
- non-admin 403
- HostEventBroker subscribe + publish 단위 동작 (HTTP 통합은 ASGITransport
  스트리밍 한계로 broker 단위로만 검증; 운영에서는 sse-starlette + uvicorn 정상)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from broker.app.services.host_events import HostEventBroker
from httpx import AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


@pytest.mark.asyncio
async def test_sse_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/events/hosts")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_sse_non_admin_forbidden(auth_client: AuthClientFactory) -> None:
    user = await auth_client(role="user")
    r = await user.get("/api/v1/events/hosts")
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_broker_subscribe_receives_publish() -> None:
    """HostEventBroker.subscribe → publish 한 건이 그대로 전달."""
    broker = HostEventBroker()
    received: list[dict[str, object]] = []

    async def _consume() -> None:
        async for ev in broker.subscribe():
            received.append(ev)
            return

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0.05)
    await broker.publish({"event": "host.status", "host_id": 1, "new": "IDLE"})
    await asyncio.wait_for(consumer, timeout=2.0)
    assert received == [{"event": "host.status", "host_id": 1, "new": "IDLE"}]


@pytest.mark.asyncio
async def test_broker_publish_fans_out_to_multiple_subscribers() -> None:
    """publish 1건은 모든 subscriber에 전달."""
    broker = HostEventBroker()
    a: list[dict[str, object]] = []
    b: list[dict[str, object]] = []

    async def _consume(target: list[dict[str, object]]) -> None:
        async for ev in broker.subscribe():
            target.append(ev)
            return

    ta = asyncio.create_task(_consume(a))
    tb = asyncio.create_task(_consume(b))
    await asyncio.sleep(0.05)
    await broker.publish({"event": "host.status", "host_id": 2, "new": "OFFLINE"})
    await asyncio.gather(asyncio.wait_for(ta, timeout=2.0), asyncio.wait_for(tb, timeout=2.0))
    assert len(a) == 1
    assert len(b) == 1


@pytest.mark.asyncio
async def test_broker_close_makes_publish_noop() -> None:
    """close 후 publish는 noop — 라우터 teardown 안전."""
    broker = HostEventBroker()
    await broker.close()
    await broker.publish({"event": "x", "data": "y"})  # no exception
    assert broker.subscriber_count == 0
