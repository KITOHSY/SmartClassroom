"""GPU 메트릭 수집 — `nvidia-smi` shell-out.

v1은 NVIDIA만. NVML 바인딩(pynvml)은 GPU 메트릭 SLA가 필요해질 때 도입.
nvidia-smi 미설치/실행 실패 시 빈 리스트 반환 — heartbeat는 정상 진행.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TypedDict

NVIDIA_SMI_QUERY = (
    "name,utilization.gpu,memory.used,memory.total,temperature.gpu"
)


class GpuSnapshot(TypedDict):
    name: str
    util_pct: float
    mem_pct: float
    temp_c: float | None


def collect_gpu(*, timeout_sec: float = 5.0) -> list[GpuSnapshot]:
    """`nvidia-smi --query-gpu=...` 출력 파싱. 실패하면 [] 반환."""
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return []
    try:
        completed = subprocess.run(  # noqa: S603 — known executable path from shutil.which
            [
                nvidia_smi,
                f"--query-gpu={NVIDIA_SMI_QUERY}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if completed.returncode != 0:
        return []
    return _parse_nvidia_smi(completed.stdout)


def _parse_nvidia_smi(stdout: str) -> list[GpuSnapshot]:
    rows: list[GpuSnapshot] = []
    for line in stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            mem_used = float(parts[2])
            mem_total = float(parts[3])
            mem_pct = (mem_used / mem_total) * 100.0 if mem_total > 0 else 0.0
            rows.append(
                GpuSnapshot(
                    name=parts[0],
                    util_pct=float(parts[1]),
                    mem_pct=round(mem_pct, 1),
                    temp_c=float(parts[4]),
                )
            )
        except (ValueError, IndexError):
            continue
    return rows
