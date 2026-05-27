"""collectors/session.py — psutil 의존 부분을 인자 주입으로 분리해 unit 테스트.

T11 후속(connection_state): /serverinfo 폴링은 pytest-httpx로 mock.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


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


def _make_cfg(serverinfo_url: str = "http://sunshine.test:47989/serverinfo"):  # type: ignore[no-untyped-def]
    from smartclassroom_agent.config import AgentConfig

    return AgentConfig.model_validate(
        {
            "broker_url": "http://broker.test",
            "host_id": 1,
            "agent_token": "x" * 32,
            "sunshine_serverinfo_url": serverinfo_url,
        }
    )


@pytest.mark.asyncio
async def test_collect_session_no_cfg_returns_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """cfg=None이면 /serverinfo 호출 없이 connection_state='unknown'."""
    from smartclassroom_agent.collectors import session as session_mod

    monkeypatch.setattr(session_mod, "find_sunshine_running", lambda: True)
    monkeypatch.setattr(session_mod, "active_user", lambda: "alice")

    snap = await session_mod.collect_session(cfg=None)
    assert snap["connection_state"] == "unknown"
    assert snap["sunshine_running"] is True
    assert snap["active_user"] == "alice"
    assert snap["active_clients"] == 0


@pytest.mark.asyncio
async def test_collect_session_sunshine_not_running_skips_poll(
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    """Sunshine 미실행이면 loopback 호출 자체가 일어나지 않음."""
    from smartclassroom_agent.collectors import session as session_mod

    monkeypatch.setattr(session_mod, "find_sunshine_running", lambda: False)
    monkeypatch.setattr(session_mod, "active_user", lambda: None)

    snap = await session_mod.collect_session(cfg=_make_cfg())
    assert snap["connection_state"] == "unknown"
    assert snap["sunshine_running"] is False
    # /serverinfo 호출이 일어났다면 pytest-httpx가 unmatched request 에러를 냈을 것
    assert not httpx_mock.get_requests()


@pytest.mark.asyncio
async def test_collect_session_busy_returns_active(
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    from smartclassroom_agent.collectors import session as session_mod

    monkeypatch.setattr(session_mod, "find_sunshine_running", lambda: True)
    monkeypatch.setattr(session_mod, "active_user", lambda: None)

    cfg = _make_cfg()
    httpx_mock.add_response(
        url=str(cfg.sunshine_serverinfo_url),
        text="<root><state>SUNSHINE_SERVER_BUSY</state><currentgame>42</currentgame></root>",
    )
    snap = await session_mod.collect_session(cfg=cfg)
    assert snap["connection_state"] == "active"


@pytest.mark.asyncio
async def test_collect_session_free_returns_disconnected(
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    from smartclassroom_agent.collectors import session as session_mod

    monkeypatch.setattr(session_mod, "find_sunshine_running", lambda: True)
    monkeypatch.setattr(session_mod, "active_user", lambda: None)

    cfg = _make_cfg()
    httpx_mock.add_response(
        url=str(cfg.sunshine_serverinfo_url),
        text="<root><state>SUNSHINE_SERVER_FREE</state><currentgame>0</currentgame></root>",
    )
    snap = await session_mod.collect_session(cfg=cfg)
    assert snap["connection_state"] == "disconnected"


@pytest.mark.asyncio
async def test_collect_session_non_200_returns_unknown(
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    from smartclassroom_agent.collectors import session as session_mod

    monkeypatch.setattr(session_mod, "find_sunshine_running", lambda: True)
    monkeypatch.setattr(session_mod, "active_user", lambda: None)

    cfg = _make_cfg()
    httpx_mock.add_response(url=str(cfg.sunshine_serverinfo_url), status_code=500)
    snap = await session_mod.collect_session(cfg=cfg)
    assert snap["connection_state"] == "unknown"


@pytest.mark.asyncio
async def test_collect_session_missing_state_tag_returns_unknown(
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    from smartclassroom_agent.collectors import session as session_mod

    monkeypatch.setattr(session_mod, "find_sunshine_running", lambda: True)
    monkeypatch.setattr(session_mod, "active_user", lambda: None)

    cfg = _make_cfg()
    httpx_mock.add_response(
        url=str(cfg.sunshine_serverinfo_url),
        text="<root><currentgame>0</currentgame></root>",
    )
    snap = await session_mod.collect_session(cfg=cfg)
    assert snap["connection_state"] == "unknown"
