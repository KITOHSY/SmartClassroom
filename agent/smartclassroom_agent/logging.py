"""구조적 로깅 설정 — structlog JSON (broker와 일관)."""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog


def configure_logging(level: str = "INFO") -> None:
    """structlog + stdlib logging을 JSON으로 일원화.

    호출 멱등 — 여러 번 호출해도 핸들러 중복되지 않게 root 핸들러 초기화.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(log_level)
    root.addHandler(handler)
    root.setLevel(log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
