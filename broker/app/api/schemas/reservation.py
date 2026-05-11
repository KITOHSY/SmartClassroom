"""T05 예약 도메인 Pydantic 스키마.

- ReservationCreate: 요청 본문 — host_id + starts_at + ends_at.
- ReservationRead: 응답 — 외부 노출 필드.
- ReservationListQuery: GET /reservations 쿼리 — admin은 user_id 지정 가능.
- CalendarMatrix: GET /reservations/calendar — 30분 슬롯 그리드.

검증 규칙(여기서 잡는 것):
- starts_at/ends_at은 timezone-aware (naive datetime → 422)
- 30분 boundary (minute in (0,30), second/microsecond == 0) → 422
- starts_at < ends_at → 422

window 정책(과거 시작, lookahead, duration, quota)은 서비스 레이어가 검증.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _ensure_grid(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name}는 timezone 정보가 필요합니다")
    if value.minute not in (0, 30) or value.second != 0 or value.microsecond != 0:
        raise ValueError(f"{field_name}는 30분 그리드(:00 또는 :30)에 정렬되어야 합니다")
    return value


class ReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_id: int = Field(..., gt=0, description="대상 호스트 PK")
    starts_at: datetime = Field(..., description="예약 시작(timezone-aware, 30분 그리드)")
    ends_at: datetime = Field(..., description="예약 종료(timezone-aware, 30분 그리드)")

    @field_validator("starts_at", "ends_at", mode="after")
    @classmethod
    def _validate_grid(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "datetime")
        return _ensure_grid(value, field_name)

    @model_validator(mode="after")
    def _validate_order(self) -> ReservationCreate:
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at은 ends_at보다 이전이어야 합니다")
        return self


ReservationStatus = Literal["CONFIRMED", "CANCELED", "COMPLETED"]


class ReservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    host_id: int
    starts_at: datetime
    ends_at: datetime
    status: ReservationStatus
    created_at: datetime
    canceled_at: datetime | None = None


class ReservationListQuery(BaseModel):
    """GET /reservations 쿼리. router에서 Query()로 펼친 뒤 서비스에 전달."""

    from_: datetime | None = None
    to_: datetime | None = None
    host_id: int | None = None
    user_id: int | None = None  # admin만 의미 있음


class CalendarSlot(BaseModel):
    """캘린더 셀. user_id는 본인 또는 admin일 때만 노출, 그 외 None(masking)."""

    starts_at: datetime
    ends_at: datetime
    host_id: int
    reservation_id: int | None = None
    user_id: int | None = None
    status: Literal["OPEN", "OCCUPIED"] = "OPEN"


class CalendarMatrix(BaseModel):
    from_: datetime
    to_: datetime
    slot_minutes: int
    slots: list[CalendarSlot]
