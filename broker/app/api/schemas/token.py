"""T07 동적 접속 토큰 Pydantic 스키마.

- ConnectTokenResponse: POST /reservations/{id}/connect 응답 — raw 토큰 + host 접속정보 임베딩.
- HostConnectionInfo: T17이 moonlight URL 조립에 필요한 호스트 필드(ip/port).
- TokenVerifyRequest: POST /tokens/verify 요청 — token raw + consume 플래그.
- TokenVerifyResponse: 검증 결과 — 200 OK + valid bool (HTTPException 안 씀).

raw 토큰은 발급 응답에만 노출. DB는 sha256(raw) 64자(jti)만 저장.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HostConnectionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str
    ip_address: str | None = None
    sunshine_port: int

    @field_validator("ip_address", mode="before")
    @classmethod
    def _normalize_ip(cls, value: Any) -> str | None:
        # asyncpg는 INET을 str 또는 ipaddress.IPv4Address 등으로 돌려줄 수 있음.
        if value is None:
            return None
        return str(value)


class ConnectTokenResponse(BaseModel):
    token: str = Field(..., description="raw url-safe 토큰 — 발급 응답에만 노출")
    expires_at: datetime = Field(..., description="토큰 만료 = reservation.ends_at")
    reservation_id: int
    host: HostConnectionInfo


class TokenVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=16, description="검증할 raw 토큰")
    consume: bool = Field(
        default=True,
        description="True면 검증 통과 시 1회 소비 마킹(consumed_at). False면 미소비 검증.",
    )


class TokenVerifyResponse(BaseModel):
    """검증 결과. valid=False도 200 OK — 호출자(T08/T10)가 valid 플래그로 분기."""

    valid: bool
    reason: str | None = Field(
        default=None,
        description="invalid_or_expired / already_consumed",
    )
    user_id: int | None = None
    host_id: int | None = None
    reservation_id: int | None = None
    expires_at: datetime | None = None
