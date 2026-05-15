"""Phase 0 smoke test — 패키지 import + 버전 노출.

후속 phase가 도구/모듈을 추가하면 본 파일은 그대로 두고 별도 test_*.py 추가.
"""

from __future__ import annotations


def test_package_imports() -> None:
    import smartclassroom_agent

    assert smartclassroom_agent.__version__ == "0.1.0"


def test_cli_app_exposed() -> None:
    from smartclassroom_agent.cli import app

    assert app.info.name == "smartclassroom-agent"


def test_logging_configure_idempotent() -> None:
    from smartclassroom_agent.logging import configure_logging, get_logger

    configure_logging("WARNING")
    configure_logging("INFO")
    logger = get_logger("smoke")
    logger.info("agent boot", phase=0)
