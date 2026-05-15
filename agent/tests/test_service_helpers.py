"""service.windows + service.systemd 헬퍼 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path


def test_nssm_install_args_contains_required_pieces() -> None:
    from smartclassroom_agent.service.windows import (
        SERVICE_NAME,
        build_nssm_install_args,
    )

    args = build_nssm_install_args(
        Path("C:/agent.yaml"),
        python_exe="C:/Python312/python.exe",
    )
    assert args[0] == "nssm.exe"
    assert args[1] == "install"
    assert args[2] == SERVICE_NAME
    assert "smartclassroom_agent" in args
    assert "run" in args
    assert "--config" in args
    assert args[-1] in {"C:/agent.yaml", "C:\\agent.yaml"}


def test_nssm_install_args_defaults_to_current_python() -> None:
    from smartclassroom_agent.service.windows import build_nssm_install_args

    args = build_nssm_install_args(Path("agent.yaml"))
    assert sys.executable in args


def test_install_instructions_includes_service_name() -> None:
    from smartclassroom_agent.service.windows import (
        SERVICE_NAME,
        install_instructions,
    )

    text = install_instructions(Path("agent.yaml"))
    assert SERVICE_NAME in text
    assert "nssm.exe" in text


def test_systemd_unit_contains_required_sections() -> None:
    from smartclassroom_agent.service.systemd import render_systemd_unit

    unit = render_systemd_unit(
        Path("/etc/smartclassroom/agent.yaml"),
        python_exe="/usr/bin/python3",
    )
    assert "[Unit]" in unit
    assert "[Service]" in unit
    assert "[Install]" in unit
    assert "ExecStart=/usr/bin/python3 -m smartclassroom_agent run" in unit
    assert "/etc/smartclassroom/agent.yaml" in unit
    assert "Restart=on-failure" in unit
    assert "WantedBy=multi-user.target" in unit


def test_systemd_unit_defaults_to_current_python() -> None:
    from smartclassroom_agent.service.systemd import render_systemd_unit

    unit = render_systemd_unit(Path("/etc/smartclassroom/agent.yaml"))
    assert sys.executable in unit
