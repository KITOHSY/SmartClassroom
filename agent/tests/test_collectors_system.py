"""collectors/system.py — psutil 호출만 mock, 반환 shape + 타입 검증."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import psutil
import pytest


def test_collect_system_returns_shape() -> None:
    """실제 psutil 호출 — 환경 의존 없는 키/타입만 검증."""
    from smartclassroom_agent.collectors.system import collect_system

    snap = collect_system()
    assert set(snap.keys()) == {"cpu_pct", "mem_pct", "uptime_sec", "load_avg"}
    assert isinstance(snap["cpu_pct"], float)
    assert 0.0 <= snap["cpu_pct"] <= 100.0
    assert isinstance(snap["mem_pct"], float)
    assert 0.0 <= snap["mem_pct"] <= 100.0
    assert isinstance(snap["uptime_sec"], int)
    assert snap["uptime_sec"] >= 0


def test_boot_time_is_tz_aware() -> None:
    from smartclassroom_agent.collectors.system import boot_time

    bt = boot_time()
    assert isinstance(bt, datetime)
    assert bt.tzinfo is not None


def test_collect_system_with_mocked_psutil() -> None:
    """psutil 전체 mock 후 반환값이 mock에 의존하는지 검증."""
    from smartclassroom_agent.collectors import system as sysmod

    class FakeMem:
        percent = 42.5

    with (
        patch.object(psutil, "cpu_percent", return_value=12.5),
        patch.object(psutil, "virtual_memory", return_value=FakeMem),
        patch.object(psutil, "boot_time", return_value=0.0),
    ):
        snap = sysmod.collect_system()
        assert snap["cpu_pct"] == pytest.approx(12.5)
        assert snap["mem_pct"] == pytest.approx(42.5)
        assert snap["uptime_sec"] > 0
