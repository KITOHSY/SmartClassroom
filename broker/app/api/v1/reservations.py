"""T05 예약 API 라우터.

- POST   /reservations              생성 (201)
- GET    /reservations              본인 예약 리스트 (admin은 user_id 필터)
- GET    /reservations/calendar     30분 슬롯 매트릭스
- GET    /reservations/{id}         단건
- DELETE /reservations/{id}         취소 (204, 본인 또는 admin)

서비스 도메인 예외 매핑:
- ReservationConflictError       → 409 (errors.py 핸들러)
- ReservationQuotaError          → 429 (errors.py 핸들러)
- InvalidReservationWindowError  → 422 (errors.py 핸들러)
- NotOwnerError                  → 404 (router 내부 변환, 존재 노출 방지)
- ReservationNotFoundError       → 404
- HostNotFoundError              → 422
"""

from __future__ import annotations

from datetime import datetime

from broker.app.api.deps import get_current_user, get_db
from broker.app.api.schemas.reservation import (
    CalendarMatrix,
    ReservationCreate,
    ReservationRead,
)
from broker.app.core.errors import InvalidReservationWindowError
from broker.app.domain.reservation import Reservation
from broker.app.domain.user import User
from broker.app.services import reservation as reservation_service
from broker.app.services.reservation import (
    HostNotFoundError,
    NotOwnerError,
    ReservationNotFoundError,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _to_read(reservation: Reservation) -> ReservationRead:
    starts_at, ends_at = reservation_service.reservation_bounds(reservation)
    return ReservationRead(
        id=reservation.id,
        user_id=reservation.user_id,
        host_id=reservation.host_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=reservation.status,
        created_at=reservation.created_at,
        canceled_at=reservation.canceled_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ReservationRead)
async def create_reservation_endpoint(
    payload: ReservationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReservationRead:
    try:
        reservation = await reservation_service.create_reservation(
            db,
            user,
            host_id=payload.host_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
    except HostNotFoundError as exc:
        raise InvalidReservationWindowError(
            "지정한 host_id에 해당하는 호스트가 없습니다",
            detail={"host_id": payload.host_id},
        ) from exc
    await db.commit()
    return _to_read(reservation)


@router.get("", response_model=list[ReservationRead])
async def list_reservations_endpoint(
    from_: datetime | None = Query(default=None, alias="from"),
    to_: datetime | None = Query(default=None, alias="to"),
    host_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    viewer: User = Depends(get_current_user),
) -> list[ReservationRead]:
    items = await reservation_service.list_reservations(
        db,
        viewer=viewer,
        from_=from_,
        to_=to_,
        host_id=host_id,
        user_id_filter=user_id,
    )
    return [_to_read(r) for r in items]


@router.get("/calendar", response_model=CalendarMatrix)
async def calendar_endpoint(
    from_: datetime = Query(..., alias="from"),
    to_: datetime = Query(..., alias="to"),
    host_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    viewer: User = Depends(get_current_user),
) -> CalendarMatrix:
    matrix = await reservation_service.build_calendar_matrix(
        db,
        from_=from_,
        to_=to_,
        host_id=host_id,
        viewer=viewer,
    )
    return CalendarMatrix.model_validate(matrix)


@router.get("/{reservation_id}", response_model=ReservationRead)
async def get_reservation_endpoint(
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReservationRead:
    try:
        reservation = await reservation_service.get_reservation(db, user, reservation_id)
    except (ReservationNotFoundError, NotOwnerError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="예약을 찾을 수 없습니다"
        ) from exc
    return _to_read(reservation)


@router.delete("/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reservation_endpoint(
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        await reservation_service.cancel_reservation(db, user, reservation_id)
    except (ReservationNotFoundError, NotOwnerError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="예약을 찾을 수 없습니다"
        ) from exc
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
