"""collectors/session.py — psutil 의존 부분을 인자 주입으로 분리해 unit 테스트."""

from __future__ import annotations

from types import SimpleNamespace


def test_find_sunshine_running_true() -> None:
    from smartclassroom_agent.collectors.session import find_sunshine_running

    procs = [
        SimpleNamespace(info={"name": "chrome.exe"}),
        SimpleNamespace(info={"name": "Sunshine.exe"}),
    ]
    assert find_sunshine_running(procs=procs) is True


def test_find_sunshine_running_false() -> None:
    from smartclassroom_agent.collectors.session import find_sunshine_running

    procs = [SimpleNamespace(info={"name": "explorer.exe"})]
    assert find_sunshine_running(procs=procs) is False


def test_find_sunshine_handles_dead_process() -> None:
    """info dict가 비어도 예외 없이 False 반환."""
    from smartclassroom_agent.collectors.session import find_sunshine_running

    procs = [SimpleNamespace(info={})]
    assert find_sunshine_running(procs=procs) is False


def test_active_user_returns_first_console_user() -> None:
    from smartclassroom_agent.collectors.session import active_user

    users = [SimpleNamespace(name="alice"), SimpleNamespace(name="bob")]
    assert active_user(users=users) == "alice"


def test_active_user_returns_none_when_no_users() -> None:
    from smartclassroom_agent.collectors.session import active_user

    assert active_user(users=[]) is None
