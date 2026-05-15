"""Sunshine 프로세스 + 활성 사용자 세션 수집.

v1: 프로세스 존재 + 콘솔 사용자 1명. active_clients는 Sunshine API/로그 파싱이 필요해
T10 fork 이후로 미룬다 — 현재는 항상 0.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypedDict

import psutil

SUNSHINE_PROCESS_NAMES = frozenset({"sunshine", "sunshine.exe"})


class SessionSnapshot(TypedDict):
    sunshine_running: bool
    active_user: str | None
    active_clients: int


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


def collect_session() -> SessionSnapshot:
    return SessionSnapshot(
        sunshine_running=find_sunshine_running(),
        active_user=active_user(),
        active_clients=0,
    )
