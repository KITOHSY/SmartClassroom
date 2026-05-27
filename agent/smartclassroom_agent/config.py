"""에이전트 설정 — YAML 파일 로드.

스키마는 pydantic BaseModel. 환경 변수 override는 향후 필요 시 추가.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel, Field, HttpUrl


class AgentConfig(BaseModel):
    """에이전트 런타임 설정."""

    broker_url: HttpUrl
    host_id: int = Field(ge=1)
    agent_token: str = Field(min_length=16, max_length=128)
    interval_seconds: float = Field(default=30.0, ge=1.0, le=600.0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    sunshine_serverinfo_url: HttpUrl = Field(
        default=HttpUrl("http://127.0.0.1:47989/serverinfo"),
    )
    sunshine_query_timeout_seconds: float = Field(default=3.0, ge=0.5, le=30.0)

    @property
    def broker_url_str(self) -> str:
        """trailing slash 제거된 base URL — httpx base_url용."""
        return str(self.broker_url).rstrip("/")


def load_config(path: Path) -> AgentConfig:
    """YAML 파일 로드 후 AgentConfig 검증.

    파일 미존재/파싱 실패는 호출자가 처리 (FileNotFoundError / yaml.YAMLError / ValidationError).
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config file root must be a mapping: {path}")
    return AgentConfig.model_validate(cast("dict[str, object]", raw))
