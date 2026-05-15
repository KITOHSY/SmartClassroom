"""Broker HTTP 클라이언트.

Bearer agent token을 모든 요청에 자동 첨부. JSON 직렬화는 httpx 기본.
"""

from __future__ import annotations

from typing import Any, cast

import httpx


class BrokerClient:
    """단일 instance per agent process. context manager 또는 명시 close()."""

    def __init__(self, broker_url: str, agent_token: str, *, timeout_sec: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=broker_url.rstrip("/"),
            timeout=timeout_sec,
            headers={"Authorization": f"Bearer {agent_token}"},
        )

    async def post_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/agents/heartbeat — 응답 JSON dict 반환."""
        r = await self._client.post("/api/v1/agents/heartbeat", json=payload)
        r.raise_for_status()
        return cast("dict[str, Any]", r.json())

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> BrokerClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
