"""에이전트 CLI — typer 기반.

서브커맨드:
- run: heartbeat loop 영속 실행 (서비스 wrapper가 호출)
- doctor: 1회 heartbeat 후 종료 — 설정/네트워크 점검용
- install-service: Phase 7에서 본구현 — Windows pywin32 + Linux systemd unit
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="smartclassroom-agent",
    help="SmartClassroom host agent — heartbeat reporter (T11)",
    no_args_is_help=True,
)


ConfigPath = Annotated[
    Path,
    typer.Option("--config", "-c", help="YAML 설정 파일 경로"),
]


def _load_and_configure(config: Path) -> object:
    """config 로드 + 로깅 셋업. AgentConfig 반환 (타입은 cli 모듈에서 import 회피)."""
    from smartclassroom_agent.config import load_config
    from smartclassroom_agent.logging import configure_logging

    cfg = load_config(config)
    configure_logging(cfg.log_level)
    return cfg


@app.command("run")
def run_cmd(config: ConfigPath = Path("agent.yaml")) -> None:
    """heartbeat loop 영속 실행. Ctrl+C로 중단."""
    from smartclassroom_agent.client import BrokerClient
    from smartclassroom_agent.config import AgentConfig
    from smartclassroom_agent.heartbeat import run_heartbeat_loop

    cfg = _load_and_configure(config)
    assert isinstance(cfg, AgentConfig)

    async def _main() -> None:
        async with BrokerClient(cfg.broker_url_str, cfg.agent_token) as client:
            await run_heartbeat_loop(
                client,
                cfg.broker_url_str,
                interval_seconds=cfg.interval_seconds,
            )

    asyncio.run(_main())


@app.command("doctor")
def doctor_cmd(config: ConfigPath = Path("agent.yaml")) -> None:
    """1회 heartbeat 후 종료 — 설정/네트워크 점검용."""
    from smartclassroom_agent.client import BrokerClient
    from smartclassroom_agent.config import AgentConfig
    from smartclassroom_agent.heartbeat import run_heartbeat_loop

    cfg = _load_and_configure(config)
    assert isinstance(cfg, AgentConfig)

    async def _main() -> int:
        async with BrokerClient(cfg.broker_url_str, cfg.agent_token) as client:
            return await run_heartbeat_loop(
                client,
                cfg.broker_url_str,
                interval_seconds=0.1,
                max_cycles=1,
            )

    cycles = asyncio.run(_main())
    typer.echo(f"sent {cycles} heartbeat(s)")


@app.command("install-service")
def install_service_cmd(config: ConfigPath = Path("agent.yaml")) -> None:
    """OS 서비스 등록 안내 — Windows는 NSSM 명령, Linux는 systemd unit 텍스트 출력.

    실제 등록(권한 필요)은 안내된 명령을 관리자가 직접 실행.
    """
    import platform

    abs_config = config.resolve() if config.exists() else config.absolute()
    if platform.system() == "Windows":
        from smartclassroom_agent.service.windows import install_instructions

        typer.echo(install_instructions(abs_config))
    else:
        from smartclassroom_agent.service.systemd import UNIT_NAME, render_systemd_unit

        typer.echo(
            f"# Linux systemd unit. /etc/systemd/system/{UNIT_NAME} 에 저장 후\n"
            "# sudo systemctl daemon-reload && sudo systemctl enable --now "
            f"{UNIT_NAME}\n"
        )
        typer.echo(render_systemd_unit(abs_config))
