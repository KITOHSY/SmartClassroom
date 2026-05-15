"""T06 — 호스트 상태 변화 SSE 이벤트 broker.

단일 broker 인스턴스 가정 (멀티 인스턴스는 §11 A10 후속).
in-process asyncio.Queue per subscriber. slow consumer는 가장 오래된 이벤트부터 drop.
publish 호출자는 await만, 큐가 가득 차도 라우터를 막지 않는다.
"""

from __future__ import annotations

import contextlib
from asyncio import Queue, QueueFull
from collections.abc import AsyncIterator
from typing import Any

import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class HostEventBroker:
    """asyncio.Queue subscriber list. publish는 모든 subscriber에 fan-out."""

    QUEUE_MAXSIZE = 100

    def __init__(self) -> None:
        self._subscribers: list[Queue[dict[str, Any]]] = []
        self._closed = False

    async def publish(self, event: dict[str, Any]) -> None:
        """모든 subscriber 큐에 이벤트 enqueue. 큐 full이면 가장 오래된 1건 drop 후 재시도.

        broker가 close된 경우 noop (테스트 teardown 안전).
        """
        if self._closed:
            return
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except QueueFull:
                # slow consumer 방어 — 가장 오래된 1건 버리고 다시 시도.
                with contextlib.suppress(Exception):
                    queue.get_nowait()
                try:
                    queue.put_nowait(event)
                except QueueFull:
                    logger.warning("host_event_dropped", event_kind=event.get("event"))

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """async generator — 새 큐 등록 후 이벤트 yield, finally로 큐 제거.

        cancel scope 안전 — sse-starlette EventSourceResponse가 client disconnect 시
        본 generator를 close하면 finally 블록이 실행되어 큐 정리.
        """
        queue: Queue[dict[str, Any]] = Queue(maxsize=self.QUEUE_MAXSIZE)
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(queue)

    async def close(self) -> None:
        """lifespan shutdown — 새 publish/subscribe 차단.

        진행 중인 subscribe generator는 다음 await에서 그대로 대기 — uvicorn이 task를
        cancel하면 자연스럽게 finally가 실행된다.
        """
        self._closed = True
        self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
