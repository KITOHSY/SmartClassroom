"""호스트 메타데이터 Pydantic 스키마.

- HostRead: GET /api/v1/hosts 응답 행. 캘린더 host 축 라벨 + 향후 가용성 표시용 최소 필드.
- HostCreate: POST /api/v1/hosts(admin) — 호스트 등록 요청 본문.
- HostWithAgentToken: POST /api/v1/hosts / POST /api/v1/hosts/{id}/agent-token 응답.
  Raw agent token을 **1회 응답에만** 노출 — DB는 sha256(raw)만 보관(T11).
- T07의 `HostConnectionInfo`(token.py)와 의도가 다름 — 본 스키마는 운영 메타
  (display_name/location/status) 중심, 접속 정보(ip/port)는 별도. 둘은 동시에 발전.

T16 (프런트 v1) 차단 요소 해소 + T11 admin enrollment 추가. T06 본구현 시 ingest/상태머신/
필터(/hosts/available) 추가하며 schema도 보강(추가 필드 / 마스킹).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str
    display_name: str
    location: str | None = None
    status: str
    sunshine_port: int

    @field_validator("location", mode="before")
    @classmethod
    def _normalize_location(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


class HostCreate(BaseModel):
    hostname: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=128)
    ip_address: str | None = None
    sunshine_port: int = Field(default=47984, ge=1, le=65535)
    gpu_model: str | None = Field(default=None, max_length=128)


class HostWithAgentToken(HostRead):
    """Host 메타 + agent token. raw 토큰은 1회 응답에만 — 서버는 sha256만 보관."""

    agent_token: str
    revoked_previous: int = 0
