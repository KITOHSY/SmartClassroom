"""호스트 메타데이터 Pydantic 스키마.

- HostRead: GET /api/v1/hosts 응답 행. 캘린더 host 축 라벨 + 향후 가용성 표시용 최소 필드.
- T07의 `HostConnectionInfo`(token.py)와 의도가 다름 — 본 스키마는 운영 메타
  (display_name/location/status) 중심, 접속 정보(ip/port)는 별도. 둘은 동시에 발전.

T16 (프런트 v1) 차단 요소만 풀기 위한 read-only 임시 노출.
T06 본구현 시 ingest/상태머신/필터(/hosts/available) 추가하며 schema도 보강.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


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
