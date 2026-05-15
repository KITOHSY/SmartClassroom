"""T06 — 호스트 상태 변화 SSE 채널 (관리자용).

GET /api/v1/events/hosts — `text/event-stream` 응답.
- 인증: admin 한정 (`require_admin`).
- 페이로드: HostEventBroker.publish가 보내는 dict — `{"event":"host.status", ...}`.
- 단일 broker 인스턴스 가정 (멀티 인스턴스는 §11 A10 후속).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from broker.app.api.deps import get_host_event_broker, require_admin
from broker.app.domain.user import User
from broker.app.services.host_events import HostEventBroker
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


@router.get("/hosts")
async def stream_host_events(
    request: Request,
    _admin: User = Depends(require_admin),
    broker: HostEventBroker = Depends(get_host_event_broker),
) -> EventSourceResponse:
    """관리자가 호스트 상태 변화를 실시간으로 구독."""

    async def _generator() -> AsyncIterator[dict[str, Any]]:
        # 첫 chunk를 즉시 보내 ASGITransport/프록시가 stream을 흘려보내기 시작하게 함.
        yield {"event": "ready", "data": "{}"}
        async for event in broker.subscribe():
            if await request.is_disconnected():
                break
            # sse-starlette은 dict {event, data, ...}를 SSE wire format으로 변환.
            yield {"event": str(event.get("event", "message")), "data": json.dumps(event)}

    return EventSourceResponse(_generator(), ping=2)
