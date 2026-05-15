"""T06 — `evaluate_host_status` 순수 함수 단위 테스트.

DB 의존성 없음. Settings는 직접 인스턴스화.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from broker.app.core.config import Settings
from broker.app.services.host_status import evaluate_host_status


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "session_secret": "x" * 32,
        "host_offline_after_seconds": 90,
        "host_degraded_cpu_pct": 90.0,
        "host_degraded_mem_pct": 95.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC)


def _kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "now": NOW,
        "last_heartbeat_at": NOW,
        "has_active_reservation": False,
        "sunshine_running": False,
        "cpu_pct": 10.0,
        "mem_pct": 30.0,
        "settings": _settings(),
    }
    base.update(overrides)
    return base


def test_no_heartbeat_yields_offline() -> None:
    assert evaluate_host_status(**_kwargs(last_heartbeat_at=None)) == "OFFLINE"  # type: ignore[arg-type]


def test_stale_heartbeat_beyond_threshold_yields_offline() -> None:
    stale = NOW - timedelta(seconds=91)
    assert evaluate_host_status(**_kwargs(last_heartbeat_at=stale)) == "OFFLINE"  # type: ignore[arg-type]


def test_heartbeat_just_within_threshold_yields_idle() -> None:
    fresh = NOW - timedelta(seconds=89)
    assert evaluate_host_status(**_kwargs(last_heartbeat_at=fresh)) == "IDLE"  # type: ignore[arg-type]


def test_active_reservation_with_sunshine_yields_in_use() -> None:
    assert (
        evaluate_host_status(
            **_kwargs(has_active_reservation=True, sunshine_running=True)  # type: ignore[arg-type]
        )
        == "IN_USE"
    )


def test_active_reservation_without_sunshine_yields_degraded() -> None:
    """예약자가 못 접속하는 실패 신호."""
    assert (
        evaluate_host_status(
            **_kwargs(has_active_reservation=True, sunshine_running=False)  # type: ignore[arg-type]
        )
        == "DEGRADED"
    )


def test_high_cpu_yields_degraded() -> None:
    assert evaluate_host_status(**_kwargs(cpu_pct=92.0)) == "DEGRADED"  # type: ignore[arg-type]


def test_high_mem_yields_degraded() -> None:
    assert evaluate_host_status(**_kwargs(mem_pct=96.0)) == "DEGRADED"  # type: ignore[arg-type]


def test_cpu_at_threshold_yields_degraded_inclusive() -> None:
    assert evaluate_host_status(**_kwargs(cpu_pct=90.0)) == "DEGRADED"  # type: ignore[arg-type]


def test_normal_load_no_reservation_yields_idle() -> None:
    assert evaluate_host_status(**_kwargs()) == "IDLE"  # type: ignore[arg-type]


def test_none_metrics_treated_as_normal_yields_idle() -> None:
    assert evaluate_host_status(**_kwargs(cpu_pct=None, mem_pct=None)) == "IDLE"  # type: ignore[arg-type]


def test_offline_priority_over_active_reservation() -> None:
    """heartbeat 누락이 가장 높은 우선순위 — 예약 활성이어도 OFFLINE."""
    assert (
        evaluate_host_status(
            **_kwargs(  # type: ignore[arg-type]
                last_heartbeat_at=None,
                has_active_reservation=True,
                sunshine_running=True,
            )
        )
        == "OFFLINE"
    )


def test_in_use_priority_over_high_load() -> None:
    """예약 활성 + sunshine 실행은 부하 임계와 무관하게 IN_USE."""
    assert (
        evaluate_host_status(
            **_kwargs(  # type: ignore[arg-type]
                has_active_reservation=True,
                sunshine_running=True,
                cpu_pct=99.0,
                mem_pct=99.0,
            )
        )
        == "IN_USE"
    )


def test_custom_offline_threshold_via_settings() -> None:
    short = _settings(host_offline_after_seconds=10)
    stale_for_short = NOW - timedelta(seconds=11)
    assert (
        evaluate_host_status(**_kwargs(settings=short, last_heartbeat_at=stale_for_short))  # type: ignore[arg-type]
        == "OFFLINE"
    )


@pytest.mark.parametrize("status", ["OFFLINE", "IDLE", "IN_USE", "DEGRADED"])
def test_status_literal_in_constant(status: str) -> None:
    from broker.app.services.host_status import HOST_STATES

    assert status in HOST_STATES
