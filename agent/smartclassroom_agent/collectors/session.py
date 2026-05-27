"""Sunshine 프로세스 + 활성 사용자 세션 수집.

v1: 프로세스 존재 + 콘솔 사용자 1명. active_clients는 Sunshine API/로그 파싱이 필요해
T10 fork 이후로 미룬다 — 현재는 항상 0.

T11 후속(connection_state): Sunshine `/serverinfo` (port 47989, 무인증) 폴링으로
"현재 스트림 active 여부"를 active|disconnected|unknown로 판정. T09 암묵 종료 감지의
주 채널. 응답 XML의 `<state>SUNSHINE_SERVER_BUSY|FREE</state>`만 본다.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, TypedDict

import httpx
import psutil

from smartclassroom_agent.logging import get_logger

if TYPE_CHECKING:
    from smartclassroom_agent.config import AgentConfig

logger = get_logger(__name__)

SUNSHINE_PROCESS_NAMES = frozenset({"sunshine", "sunshine.exe"})

_STATE_RE = re.compile(r"<state>([^<]+)</state>", re.IGNORECASE)


class SessionSnapshot(TypedDict):
    sunshine_running: bool
    active_user: str | None
    active_clients: int
    connection_state: str


def _process_name(proc: Any) -> str:
    """psutil.Process에서 안전하게 이름 추출."""
    info = getattr(proc, "info", None)
    if isinstance(info, dict):
        name = info.get("name")
        if isinstance(name, str):
            return name
    try:
        result = proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
        return ""
    return str(result) if isinstance(result, str) else ""


def find_sunshine_running(procs: Iterable[Any] | None = None) -> bool:
    """Sunshine 프로세스 발견 시 True. procs 인자는 테스트 주입용."""
    iterator: Iterable[Any]
    iterator = procs if procs is not None else psutil.process_iter(["name"])
    for p in iterator:
        name = _process_name(p).lower()
        if name in SUNSHINE_PROCESS_NAMES:
            return True
    return False


def active_user(users: list[Any] | None = None) -> str | None:
    """첫 콘솔 사용자 이름. 없으면 None. users 인자는 테스트 주입용."""
    rows = users if users is not None else psutil.users()
    if not rows:
        return None
    name = getattr(rows[0], "name", None)
    return str(name) if isinstance(name, str) else None


async def _query_sunshine_serverinfo(cfg: AgentConfig) -> str:
    try:
        async with httpx.AsyncClient(timeout=cfg.sunshine_query_timeout_seconds) as client:
            resp = await client.get(str(cfg.sunshine_serverinfo_url))
    except Exception as exc:
        logger.warning(
            "sunshine_serverinfo poll failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return "unknown"
    if resp.status_code != 200:
        logger.warning("sunshine_serverinfo non-200", status=resp.status_code)
        return "unknown"
    match = _STATE_RE.search(resp.text)
    if match is None:
        logger.warning("sunshine_serverinfo missing <state>")
        return "unknown"
    state = match.group(1).strip()
    if state == "SUNSHINE_SERVER_BUSY":
        return "active"
    if state == "SUNSHINE_SERVER_FREE":
        return "disconnected"
    logger.warning("sunshine_serverinfo unknown state", state=state)
    return "unknown"


async def collect_session(*, cfg: AgentConfig | None = None) -> SessionSnapshot:
    """세션 정보 수집.

    cfg가 주어지고 Sunshine 프로세스가 떠 있으면 /serverinfo 폴링으로 connection_state 판정.
    cfg=None 또는 sunshine 미실행이면 connection_state="unknown" (loopback 호출 회피).
    """
    sunshine_running = await asyncio.to_thread(find_sunshine_running)
    user = await asyncio.to_thread(active_user)
    if not sunshine_running or cfg is None:
        connection_state = "unknown"
    else:
        connection_state = await _query_sunshine_serverinfo(cfg)
    return SessionSnapshot(
        sunshine_running=sunshine_running,
        active_user=user,
        active_clients=0,
        connection_state=connection_state,
    )
