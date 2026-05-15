"""systemd unit 파일 생성 헬퍼 (Linux 테스트/특수 환경용).

설치 절차:
    1) `python -m smartclassroom_agent install-service --config /etc/smartclassroom/agent.yaml`
       명령이 unit content를 stdout으로 출력
    2) `sudo tee /etc/systemd/system/smartclassroom-agent.service` 로 저장
    3) `sudo systemctl daemon-reload && sudo systemctl enable --now smartclassroom-agent`

User=/Group= 는 환경마다 달라 본 헬퍼에서는 비워둠 — 호출자가 필요 시 후처리.
"""

from __future__ import annotations

import sys
from pathlib import Path

UNIT_NAME = "smartclassroom-agent.service"
UNIT_TEMPLATE = """\
[Unit]
Description=SmartClassroom host agent (T11)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python_exe} -m smartclassroom_agent run --config {config_path}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def render_systemd_unit(
    config_path: Path,
    *,
    python_exe: str | None = None,
) -> str:
    """unit 파일 텍스트 반환. 파일 저장은 호출자 책임.

    config_path는 POSIX 표현으로 직렬화 — systemd unit은 Linux 전용이라
    Windows에서 생성해도 forward-slash가 자연스럽다.
    """
    py = python_exe or sys.executable
    return UNIT_TEMPLATE.format(python_exe=py, config_path=config_path.as_posix())
