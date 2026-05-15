"""collectors/gpu.py — nvidia-smi CSV 파서 단위 + shell-out 부재 시 빈 리스트."""

from __future__ import annotations

from unittest.mock import patch


def test_parse_nvidia_smi_two_gpus() -> None:
    from smartclassroom_agent.collectors.gpu import _parse_nvidia_smi

    stdout = (
        "NVIDIA GeForce RTX 3060, 42, 2048, 12288, 51\n"
        "NVIDIA GeForce RTX 4090, 88, 16384, 24576, 71\n"
    )
    rows = _parse_nvidia_smi(stdout)
    assert len(rows) == 2
    assert rows[0]["name"] == "NVIDIA GeForce RTX 3060"
    assert rows[0]["util_pct"] == 42.0
    assert rows[0]["mem_pct"] == 16.7  # 2048/12288 = 16.67%
    assert rows[0]["temp_c"] == 51.0


def test_parse_nvidia_smi_skips_malformed_lines() -> None:
    from smartclassroom_agent.collectors.gpu import _parse_nvidia_smi

    stdout = "NVIDIA GPU, 50, 4096, 8192, 60\nincomplete\n"
    rows = _parse_nvidia_smi(stdout)
    assert len(rows) == 1


def test_collect_gpu_returns_empty_when_nvidia_smi_missing() -> None:
    from smartclassroom_agent.collectors import gpu as gpu_mod

    with patch.object(gpu_mod.shutil, "which", return_value=None):
        assert gpu_mod.collect_gpu() == []
