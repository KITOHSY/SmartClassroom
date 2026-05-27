"""config.py — YAML 로드 + 검증."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "agent.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_valid_config(tmp_path: Path) -> None:
    from smartclassroom_agent.config import load_config

    path = _write(
        tmp_path,
        "broker_url: http://broker.test\n"
        "host_id: 42\n"
        "agent_token: " + ("x" * 32) + "\n"
        "interval_seconds: 15.0\n"
        "log_level: DEBUG\n",
    )
    cfg = load_config(path)
    assert cfg.host_id == 42
    assert cfg.broker_url_str == "http://broker.test"
    assert cfg.interval_seconds == 15.0
    assert cfg.log_level == "DEBUG"


def test_default_values_applied(tmp_path: Path) -> None:
    from smartclassroom_agent.config import load_config

    path = _write(
        tmp_path,
        "broker_url: https://broker.example.com\nhost_id: 1\nagent_token: " + ("a" * 32) + "\n",
    )
    cfg = load_config(path)
    assert cfg.interval_seconds == 30.0
    assert cfg.log_level == "INFO"


def test_missing_required_field_raises(tmp_path: Path) -> None:
    from smartclassroom_agent.config import load_config

    path = _write(tmp_path, "broker_url: http://x\nhost_id: 1\n")
    with pytest.raises(ValidationError):
        load_config(path)


def test_interval_out_of_range_raises(tmp_path: Path) -> None:
    from smartclassroom_agent.config import load_config

    path = _write(
        tmp_path,
        "broker_url: http://x\n"
        "host_id: 1\n"
        "agent_token: " + ("a" * 32) + "\n"
        "interval_seconds: 0.5\n",
    )
    with pytest.raises(ValidationError):
        load_config(path)


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    from smartclassroom_agent.config import load_config

    path = _write(tmp_path, "- broker_url: http://x\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_config(path)


def test_sunshine_defaults_applied(tmp_path: Path) -> None:
    """T11 후속 — Sunshine 폴링 필드 기본값."""
    from smartclassroom_agent.config import load_config

    path = _write(
        tmp_path,
        "broker_url: http://broker.test\nhost_id: 1\nagent_token: " + ("a" * 32) + "\n",
    )
    cfg = load_config(path)
    assert str(cfg.sunshine_serverinfo_url) == "http://127.0.0.1:47989/serverinfo"
    assert cfg.sunshine_query_timeout_seconds == 3.0


def test_sunshine_serverinfo_override(tmp_path: Path) -> None:
    from smartclassroom_agent.config import load_config

    path = _write(
        tmp_path,
        "broker_url: http://broker.test\n"
        "host_id: 1\n"
        "agent_token: " + ("a" * 32) + "\n"
        "sunshine_serverinfo_url: http://localhost:47989/serverinfo\n"
        "sunshine_query_timeout_seconds: 5.0\n",
    )
    cfg = load_config(path)
    assert "localhost" in str(cfg.sunshine_serverinfo_url)
    assert cfg.sunshine_query_timeout_seconds == 5.0
