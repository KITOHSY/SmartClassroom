"""cli doctor — 1회 heartbeat 실행 (typer CliRunner + pytest-httpx)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


def _agent_yaml(tmp_path: Path, broker_url: str) -> Path:
    p = tmp_path / "agent.yaml"
    p.write_text(
        f"broker_url: {broker_url}\n"
        "host_id: 1\n"
        "agent_token: " + ("a" * 32) + "\n",
        encoding="utf-8",
    )
    return p


def test_doctor_invokes_one_heartbeat(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    from smartclassroom_agent.cli import app

    httpx_mock.add_response(url="http://broker.test/healthz", json={"status": "ok"})
    httpx_mock.add_response(
        url="http://broker.test/api/v1/agents/heartbeat",
        method="POST",
        json={"next_interval_sec": 30, "server_time": "2026-05-14T00:00:00+00:00"},
    )

    cfg = _agent_yaml(tmp_path, "http://broker.test")
    runner = CliRunner()
    result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "sent 1 heartbeat" in result.output


def test_install_service_outputs_os_specific_instructions(tmp_path: Path) -> None:
    """OS별로 NSSM 명령 또는 systemd unit content 출력 (exit 0)."""
    import platform

    from smartclassroom_agent.cli import app

    cfg = _agent_yaml(tmp_path, "http://broker.test")
    runner = CliRunner()
    result = runner.invoke(app, ["install-service", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    if platform.system() == "Windows":
        assert "nssm.exe" in result.output
        assert "SmartClassroomAgent" in result.output
    else:
        assert "[Unit]" in result.output
        assert "ExecStart=" in result.output
