"""Windows 서비스 등록 헬퍼.

v1은 NSSM(Non-Sucking Service Manager) 등록 명령을 빌드한다 — pywin32 ServiceFramework
직접 통합은 install-service 후속 작업. NSSM은 외부 도구라 인스톨러가 별도로 배포.

설치 절차:
    1) NSSM 다운로드 → nssm.exe를 PATH에 두거나 절대경로 지정
    2) 관리자 cmd:
       nssm.exe install SmartClassroomAgent "<python>" -m smartclassroom_agent run --config <path>
       nssm.exe start SmartClassroomAgent
    3) 제거:
       nssm.exe stop SmartClassroomAgent && nssm.exe remove SmartClassroomAgent confirm

본 모듈은 import만으로는 Windows API에 의존하지 않는다 — Linux 환경에서도 import 가능.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_NAME = "SmartClassroomAgent"
SERVICE_DISPLAY_NAME = "SmartClassroom Host Agent"


def build_nssm_install_args(
    config_path: Path,
    *,
    python_exe: str | None = None,
    nssm_path: str = "nssm.exe",
) -> list[str]:
    """NSSM 등록 명령 인자 리스트. 호출자가 subprocess.run 또는 echo.

    Example:
        ["nssm.exe", "install", "SmartClassroomAgent",
         "C:/Python312/python.exe", "-m", "smartclassroom_agent",
         "run", "--config", "C:/agent.yaml"]
    """
    py = python_exe or sys.executable
    return [
        nssm_path,
        "install",
        SERVICE_NAME,
        py,
        "-m",
        "smartclassroom_agent",
        "run",
        "--config",
        str(config_path),
    ]


def install_instructions(config_path: Path) -> str:
    """관리자에게 출력할 설치 안내 텍스트."""
    args = build_nssm_install_args(config_path)
    quoted = " ".join(f'"{a}"' if " " in a else a for a in args)
    return (
        "Windows 서비스 등록 절차 (NSSM):\n"
        "  1) https://nssm.cc/ 에서 nssm.exe 다운로드 후 PATH에 두기\n"
        "  2) 관리자 cmd 에서 실행:\n"
        f"     {quoted}\n"
        f"     nssm.exe start {SERVICE_NAME}\n"
        "  3) 제거: nssm.exe stop ... && nssm.exe remove ... confirm\n"
    )
