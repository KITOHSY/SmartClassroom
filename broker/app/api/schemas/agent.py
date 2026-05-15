"""T11 heartbeat 요청/응답 스키마.

- HeartbeatRequest는 호스트 측 에이전트가 30초 주기로 보내는 페이로드.
- 응답은 dict 형태(`HeartbeatResponse`) — 향후 T06 본구현에서 명령 채널을 얹을 수 있게.
- cpu/gpu 수치는 hosts.host_metadata JSONB에 저장. 컬럼 분리는 T06 본구현 판단.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemMetrics(BaseModel):
    cpu_pct: float = Field(ge=0.0, le=100.0)
    mem_pct: float = Field(ge=0.0, le=100.0)
    uptime_sec: int = Field(ge=0)
    load_avg: list[float] | None = None


class SessionInfo(BaseModel):
    sunshine_running: bool
    active_user: str | None = Field(default=None, max_length=64)
    active_clients: int = Field(default=0, ge=0)


class GpuMetric(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(min_length=1, max_length=128)
    util_pct: float = Field(ge=0.0, le=100.0)
    mem_pct: float = Field(ge=0.0, le=100.0)
    temp_c: float | None = None


class HeartbeatRequest(BaseModel):
    agent_version: str = Field(min_length=1, max_length=32)
    boot_time: datetime
    system: SystemMetrics
    session: SessionInfo
    gpu: list[GpuMetric] | None = None
    agent_self_rtt_ms: float | None = Field(default=None, ge=0.0)


class HeartbeatResponse(BaseModel):
    next_interval_sec: int = 30
    server_time: datetime
