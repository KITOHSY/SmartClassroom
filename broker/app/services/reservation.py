"""T05 예약 도메인 서비스.

비즈니스 로직 1파일 — 추상화 최소화. CRUD + 캘린더 매트릭스 + 검증 헬퍼.

- create_reservation: boundary/window/quota 검증 → INSERT → IntegrityError → 409.
- cancel_reservation: 본인 또는 admin → soft delete (status='CANCELED' + canceled_at).
  EXCLUDE 제약이 CANCELED 행을 자동 제외하므로 같은 슬롯 재예약은 OK.
- get_reservation: 본인 또는 admin (그 외는 NotOwnerError → router가 404 매핑).
- list_reservations: 일반 사용자는 본인 것만, admin은 user_id 필터 허용.
- build_calendar_matrix: 30분 슬롯 그리드 + 활성 예약 매핑. 본인 외 user_id 마스킹.

commit은 호출자(router)가 책임진다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from broker.app.core.config import get_settings
from broker.app.core.errors import (
    InvalidReservationWindowError,
    ReservationConflictError,
    ReservationQuotaError,
)
from broker.app.domain.audit import write_audit
from broker.app.domain.host import Host
from broker.app.domain.reservation import Reservation
from broker.app.domain.user import User
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# 0001 마이그레이션 line 145-153의 EXCLUDE GIST 제약 이름. router/service 양쪽에서 비교.
RESERVATION_OVERLAP_CONSTRAINT: Final[str] = "reservations_no_overlap"

ACTIVE_RESERVATION_STATUSES: Final[tuple[str, ...]] = ("CONFIRMED", "COMPLETED")

# T17 즉시 사용 — starts_at=now ~ (now + 이 길이)가 속한 30분 슬롯 끝까지.
INSTANT_USE_DURATION: Final[timedelta] = timedelta(hours=2, minutes=30)


class NotOwnerError(Exception):
    """본인 예약이 아니거나 admin이 아닌 경우. router가 404로 변환(존재 노출 방지)."""


class ReservationNotFoundError(Exception):
    """예약이 존재하지 않음. router가 404로 변환."""


class HostNotFoundError(Exception):
    """대상 호스트가 없음. router가 422로 변환(window invalid의 일종)."""


class HostNotAvailableError(Exception):
    """T17 즉시 사용 — 호스트가 IDLE 상태가 아님. router가 409로 변환."""


# ---------------------------------------------------------------------------
# 검증 헬퍼
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _is_grid_aligned(dt: datetime, slot_minutes: int) -> bool:
    if dt.tzinfo is None:
        return False
    if slot_minutes == 30:
        return dt.minute in (0, 30) and dt.second == 0 and dt.microsecond == 0
    return dt.minute % slot_minutes == 0 and dt.second == 0 and dt.microsecond == 0


def _validate_window(starts_at: datetime, ends_at: datetime) -> None:
    settings = get_settings()
    slot_minutes = settings.reservation_slot_minutes

    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise InvalidReservationWindowError("datetime은 timezone-aware여야 합니다")
    if not _is_grid_aligned(starts_at, slot_minutes):
        raise InvalidReservationWindowError(
            f"starts_at은 {slot_minutes}분 그리드에 정렬되어야 합니다",
            detail={"field": "starts_at", "slot_minutes": slot_minutes},
        )
    if not _is_grid_aligned(ends_at, slot_minutes):
        raise InvalidReservationWindowError(
            f"ends_at은 {slot_minutes}분 그리드에 정렬되어야 합니다",
            detail={"field": "ends_at", "slot_minutes": slot_minutes},
        )
    if starts_at >= ends_at:
        raise InvalidReservationWindowError(
            "starts_at은 ends_at보다 이전이어야 합니다",
            detail={"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
        )

    duration = ends_at - starts_at
    max_duration = timedelta(minutes=settings.max_reservation_duration_minutes)
    if duration > max_duration:
        raise InvalidReservationWindowError(
            f"예약 길이는 최대 {settings.max_reservation_duration_minutes}분입니다",
            detail={
                "duration_minutes": int(duration.total_seconds() // 60),
                "max_minutes": settings.max_reservation_duration_minutes,
            },
        )

    now = _now()
    if starts_at < now:
        raise InvalidReservationWindowError(
            "과거 시각으로는 예약할 수 없습니다",
            detail={"starts_at": starts_at.isoformat(), "now": now.isoformat()},
        )

    lookahead_limit = now + timedelta(days=settings.reservation_lookahead_days)
    if starts_at > lookahead_limit:
        raise InvalidReservationWindowError(
            f"예약은 최대 {settings.reservation_lookahead_days}일 이후까지 가능합니다",
            detail={
                "starts_at": starts_at.isoformat(),
                "lookahead_days": settings.reservation_lookahead_days,
            },
        )


async def _validate_host_exists(db: AsyncSession, host_id: int) -> Host:
    host = await db.get(Host, host_id)
    if host is None:
        raise HostNotFoundError(f"host_id={host_id} 가 존재하지 않습니다")
    return host


async def _validate_quota(
    db: AsyncSession,
    *,
    user: User,
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    settings = get_settings()
    now = _now()

    # 1) 동시 활성 예약 수 (앞으로 다가올 + 진행 중) — CANCELED 제외, 종료 시각이 미래인 것만.
    concurrent_stmt = (
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.user_id == user.id,
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            text("upper(time_range) > :now").bindparams(now=now),
        )
    )
    concurrent_count = (await db.execute(concurrent_stmt)).scalar_one()
    if concurrent_count >= settings.max_concurrent_reservations:
        raise ReservationQuotaError(
            f"동시 활성 예약은 최대 {settings.max_concurrent_reservations}건입니다",
            detail={
                "limit": "concurrent",
                "current": int(concurrent_count),
                "max": settings.max_concurrent_reservations,
            },
        )

    # 2) 같은 날(예약 시작일 기준) 누적 예약 시간.
    #    starts_at의 날짜 경계로 [day_start, day_end) 윈도우를 잡아 합산.
    tz = starts_at.tzinfo
    day_start = starts_at.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    new_duration_minutes = int((ends_at - starts_at).total_seconds() // 60)

    daily_stmt = select(Reservation.time_range).where(
        Reservation.user_id == user.id,
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        text("time_range && tstzrange(:from_, :to_, '[)')").bindparams(
            from_=day_start, to_=day_end
        ),
    )
    rows = (await db.execute(daily_stmt)).scalars().all()
    used_minutes = 0
    for raw in rows:
        # asyncpg는 TSTZRANGE를 asyncpg.Range로 돌려준다. 안전하게 lower/upper 추출.
        lower = getattr(raw, "lower", None)
        upper = getattr(raw, "upper", None)
        if lower is None or upper is None:
            continue
        if lower.tzinfo is None:
            lower = lower.replace(tzinfo=tz)
        if upper.tzinfo is None:
            upper = upper.replace(tzinfo=tz)
        clipped_lower = max(lower, day_start)
        clipped_upper = min(upper, day_end)
        if clipped_upper > clipped_lower:
            used_minutes += int((clipped_upper - clipped_lower).total_seconds() // 60)

    if used_minutes + new_duration_minutes > settings.max_reservation_hours_per_day * 60:
        raise ReservationQuotaError(
            f"하루 최대 {settings.max_reservation_hours_per_day}시간까지 예약할 수 있습니다",
            detail={
                "limit": "daily_minutes",
                "used_minutes": used_minutes,
                "requested_minutes": new_duration_minutes,
                "max_minutes": settings.max_reservation_hours_per_day * 60,
            },
        )


# ---------------------------------------------------------------------------
# 핵심 동작
# ---------------------------------------------------------------------------


async def create_reservation(
    db: AsyncSession,
    user: User,
    *,
    host_id: int,
    starts_at: datetime,
    ends_at: datetime,
) -> Reservation:
    """예약 생성. 검증 실패 시 도메인 예외, 충돌 시 ReservationConflictError."""
    _validate_window(starts_at, ends_at)
    await _validate_host_exists(db, host_id)
    await _validate_quota(db, user=user, starts_at=starts_at, ends_at=ends_at)

    # TSTZRANGE는 ORM 매핑이 어색해 raw INSERT + RETURNING id로 처리.
    try:
        result = await db.execute(
            text(
                "INSERT INTO reservations (user_id, host_id, time_range, status) "
                "VALUES (:uid, :hid, tstzrange(:s, :e, '[)'), 'CONFIRMED') "
                "RETURNING id"
            ).bindparams(uid=user.id, hid=host_id, s=starts_at, e=ends_at)
        )
        new_id = result.scalar_one()
    except IntegrityError as exc:
        await db.rollback()
        if _is_overlap_violation(exc):
            raise ReservationConflictError() from exc
        raise

    reservation = await db.get(Reservation, new_id)
    if reservation is None:
        raise RuntimeError(f"INSERT RETURNING 직후 Reservation(id={new_id}) 조회 실패")

    await write_audit(
        db,
        action="reservation_create",
        actor_user_id=user.id,
        actor_kind="user",
        target_kind="reservation",
        target_id=reservation.id,
        auth_provider=user.provider,
        detail={
            "host_id": host_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
        },
    )
    return reservation


def _instant_window(
    now: datetime, next_reservation_at: datetime | None = None
) -> tuple[datetime, datetime]:
    """T17 즉시 사용 윈도우 산정.

    - starts_at = now (초 단위 절삭, 30분 그리드 미정렬 — 의도된 우회)
    - ends_at = (now + INSTANT_USE_DURATION)가 속한 30분 슬롯의 끝.
      단 `next_reservation_at`(그 호스트의 다음 예약 시작)이 더 이르면 거기서 자른다 —
      반열림 `[)`이라 경계가 맞닿아도 EXCLUDE는 겹침으로 보지 않는다.

    예: now=14:37 → now+2.5h=17:07 → 슬롯 [17:00,17:30) → ends_at=17:30.
        단 다음 예약이 15:00이면 ends_at=15:00.
    """
    starts_at = now.replace(microsecond=0)
    target = now + INSTANT_USE_DURATION
    floored = target.replace(minute=(target.minute // 30) * 30, second=0, microsecond=0)
    ends_at = floored + timedelta(minutes=30)
    if next_reservation_at is not None and next_reservation_at < ends_at:
        ends_at = next_reservation_at
    return starts_at, ends_at


async def _next_reservation_start(
    db: AsyncSession, host_id: int, *, after: datetime
) -> datetime | None:
    """host의 다음 CONFIRMED 예약 시작 시각(after 이후 가장 이른 것). 없으면 None.

    `:name::type` 캐스트 충돌 회피로 raw SQL — Postgres가 timestamptz를 추론한다.
    """
    raw = await db.scalar(
        text(
            "SELECT min(lower(time_range)) FROM reservations "
            "WHERE host_id = :hid AND status = 'CONFIRMED' "
            "AND lower(time_range) > :after"
        ).bindparams(hid=host_id, after=after)
    )
    if raw is None:
        return None
    value: datetime = raw
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


async def create_instant_reservation(db: AsyncSession, user: User, *, host_id: int) -> Reservation:
    """T17 즉시 사용 예약 생성 — 시각은 서버가 산정한다.

    create_reservation과 달리 `_validate_window`(30분 그리드/과거 시각/lookahead)를
    건너뛴다 — 윈도우가 서버 산정이라 검증 불필요. quota(`_validate_quota`)는 그대로
    적용한다(우회 대상은 그리드 제약뿐). 호스트가 IDLE이 아니면 HostNotAvailableError,
    슬롯 충돌은 EXCLUDE GIST → ReservationConflictError.
    """
    now = _now()
    host = await _validate_host_exists(db, host_id)
    if host.status != "IDLE":
        raise HostNotAvailableError(
            f"host_id={host_id} 는 IDLE 상태가 아닙니다 (status={host.status})"
        )
    # 다음 예약 시작 전까지로 윈도우를 자른다 — 그 호스트의 임박한 예약과 겹치지 않게.
    next_start = await _next_reservation_start(db, host_id, after=now)
    starts_at, ends_at = _instant_window(now, next_start)
    await _validate_quota(db, user=user, starts_at=starts_at, ends_at=ends_at)

    # create_reservation과 동일 — TSTZRANGE raw INSERT + RETURNING id.
    try:
        result = await db.execute(
            text(
                "INSERT INTO reservations (user_id, host_id, time_range, status) "
                "VALUES (:uid, :hid, tstzrange(:s, :e, '[)'), 'CONFIRMED') "
                "RETURNING id"
            ).bindparams(uid=user.id, hid=host_id, s=starts_at, e=ends_at)
        )
        new_id = result.scalar_one()
    except IntegrityError as exc:
        await db.rollback()
        if _is_overlap_violation(exc):
            raise ReservationConflictError() from exc
        raise

    reservation = await db.get(Reservation, new_id)
    if reservation is None:
        raise RuntimeError(f"INSERT RETURNING 직후 Reservation(id={new_id}) 조회 실패")

    await write_audit(
        db,
        action="reservation_create",
        actor_user_id=user.id,
        actor_kind="user",
        target_kind="reservation",
        target_id=reservation.id,
        auth_provider=user.provider,
        detail={
            "host_id": host_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "instant": True,
        },
    )
    return reservation


async def list_instant_available_hosts(db: AsyncSession) -> list[tuple[Host, datetime]]:
    """T17 바로 접속 — 지금 즉시 사용 가능한 호스트 + 각 호스트의 available_until.

    조건: status='IDLE' AND 현재 시각을 덮는 활성 예약 없음(status lag 방어).
    available_until = min(다음 CONFIRMED 예약 시작, 즉시 사용 2.5h 윈도우 끝).
    """
    now = _now()
    rows = (
        await db.execute(
            text(
                "SELECT h.id, "
                "  (SELECT min(lower(r.time_range)) FROM reservations r "
                "   WHERE r.host_id = h.id AND r.status = 'CONFIRMED' "
                "   AND lower(r.time_range) > :now) AS next_start "
                "FROM hosts h "
                "WHERE h.status = 'IDLE' "
                "  AND NOT EXISTS (SELECT 1 FROM reservations r2 "
                "    WHERE r2.host_id = h.id "
                "    AND r2.status IN ('CONFIRMED', 'COMPLETED') "
                "    AND r2.time_range @> :now) "
                "ORDER BY h.id"
            ).bindparams(now=now)
        )
    ).all()

    result: list[tuple[Host, datetime]] = []
    for host_id, next_start in rows:
        host = await db.get(Host, host_id)
        if host is None:
            continue
        next_at: datetime | None = next_start
        if next_at is not None and next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=UTC)
        _, available_until = _instant_window(now, next_at)
        result.append((host, available_until))
    return result


async def cancel_reservation(db: AsyncSession, user: User, reservation_id: int) -> Reservation:
    """예약 취소 — soft delete. 본인 또는 admin만 가능. 이미 CANCELED면 멱등."""
    reservation = await db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationNotFoundError(f"reservation_id={reservation_id} 없음")
    _assert_can_access(reservation, user)

    if reservation.status == "CANCELED":
        return reservation

    now = _now()
    await db.execute(
        update(Reservation)
        .where(Reservation.id == reservation.id)
        .values(status="CANCELED", canceled_at=now)
    )
    await db.refresh(reservation)

    await write_audit(
        db,
        action="reservation_cancel",
        actor_user_id=user.id,
        actor_kind="user",
        target_kind="reservation",
        target_id=reservation.id,
        auth_provider=user.provider,
        detail={"by": "admin" if user.role == "admin" else "owner"},
    )
    return reservation


async def get_reservation(db: AsyncSession, user: User, reservation_id: int) -> Reservation:
    reservation = await db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationNotFoundError(f"reservation_id={reservation_id} 없음")
    _assert_can_access(reservation, user)
    return reservation


async def list_reservations(
    db: AsyncSession,
    *,
    viewer: User,
    from_: datetime | None = None,
    to_: datetime | None = None,
    host_id: int | None = None,
    user_id_filter: int | None = None,
) -> list[Reservation]:
    """일반 사용자는 본인만, admin은 user_id_filter 허용. 활성 상태만 반환(CANCELED 제외)."""
    stmt = select(Reservation).where(Reservation.status.in_(ACTIVE_RESERVATION_STATUSES))

    if viewer.role == "admin":
        if user_id_filter is not None:
            stmt = stmt.where(Reservation.user_id == user_id_filter)
    else:
        # 일반 사용자는 user_id_filter를 강제로 본인으로 덮어씀(타인 user_id 무시).
        stmt = stmt.where(Reservation.user_id == viewer.id)

    if host_id is not None:
        stmt = stmt.where(Reservation.host_id == host_id)
    if from_ is not None:
        stmt = stmt.where(text("upper(time_range) > :from_").bindparams(from_=from_))
    if to_ is not None:
        stmt = stmt.where(text("lower(time_range) < :to_").bindparams(to_=to_))

    stmt = stmt.order_by(text("lower(time_range) ASC"))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def build_calendar_matrix(
    db: AsyncSession,
    *,
    from_: datetime,
    to_: datetime,
    host_id: int | None,
    viewer: User,
) -> dict[str, object]:
    """30분 슬롯 그리드 + 활성 예약 매핑. CANCELED 행 제외.

    반환: CalendarMatrix와 직렬화 호환되는 dict. router가 모델로 검증해 응답.
    user_id는 본인 또는 admin일 때만 노출, 그 외 None(마스킹).
    """
    settings = get_settings()
    slot_minutes = settings.reservation_slot_minutes

    if from_.tzinfo is None or to_.tzinfo is None:
        raise InvalidReservationWindowError("from_/to_는 timezone-aware여야 합니다")
    if not _is_grid_aligned(from_, slot_minutes) or not _is_grid_aligned(to_, slot_minutes):
        raise InvalidReservationWindowError(
            f"from_/to_는 {slot_minutes}분 그리드에 정렬되어야 합니다",
            detail={"slot_minutes": slot_minutes},
        )
    if from_ >= to_:
        raise InvalidReservationWindowError("from_은 to_보다 이전이어야 합니다")

    # 호스트 집합 (단일 host_id 또는 전체).
    if host_id is not None:
        host_ids: list[int] = [host_id]
    else:
        host_rows = (await db.execute(select(Host.id))).scalars().all()
        host_ids = list(host_rows)

    # 활성 예약 — 윈도우와 교차하는 것만.
    res_stmt = select(Reservation).where(
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        text("time_range && tstzrange(:from_, :to_, '[)')").bindparams(from_=from_, to_=to_),
    )
    if host_id is not None:
        res_stmt = res_stmt.where(Reservation.host_id == host_id)
    reservations = list((await db.execute(res_stmt)).scalars().all())

    # 예약을 (host_id, slot_start) 인덱스로 매핑.
    slot_delta = timedelta(minutes=slot_minutes)

    # Reservation.time_range가 SQLAlchemy Range/asyncpg Range로 들어옴 — lower/upper 정규화.
    def _bounds(r: Reservation) -> tuple[datetime, datetime] | None:
        raw = r.time_range
        lower = getattr(raw, "lower", None)
        upper = getattr(raw, "upper", None)
        if lower is None or upper is None:
            return None
        if lower.tzinfo is None:
            lower = lower.replace(tzinfo=UTC)
        if upper.tzinfo is None:
            upper = upper.replace(tzinfo=UTC)
        return lower, upper

    occupied: dict[tuple[int, datetime], Reservation] = {}
    for res in reservations:
        bounds = _bounds(res)
        if bounds is None:
            continue
        lower, upper = bounds
        cursor = max(lower, from_)
        # cursor를 슬롯 시작으로 내림.
        offset = (cursor - from_) % slot_delta
        if offset:
            cursor = cursor - offset
        while cursor < min(upper, to_):
            occupied[(res.host_id, cursor)] = res
            cursor += slot_delta

    slots: list[dict[str, object]] = []
    for hid in host_ids:
        cursor = from_
        while cursor < to_:
            cell_end = cursor + slot_delta
            cell: Reservation | None = occupied.get((hid, cursor))
            if cell is None:
                slots.append(
                    {
                        "starts_at": cursor,
                        "ends_at": cell_end,
                        "host_id": hid,
                        "reservation_id": None,
                        "user_id": None,
                        "status": "OPEN",
                    }
                )
            else:
                show_user = viewer.role == "admin" or cell.user_id == viewer.id
                slots.append(
                    {
                        "starts_at": cursor,
                        "ends_at": cell_end,
                        "host_id": hid,
                        "reservation_id": cell.id,
                        "user_id": cell.user_id if show_user else None,
                        "status": "OCCUPIED",
                    }
                )
            cursor = cell_end

    return {
        "from_": from_,
        "to_": to_,
        "slot_minutes": slot_minutes,
        "slots": slots,
    }


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------


def _assert_can_access(reservation: Reservation, user: User) -> None:
    if user.role == "admin":
        return
    if reservation.user_id == user.id:
        return
    raise NotOwnerError("본인 예약이 아닙니다")


def _is_overlap_violation(exc: IntegrityError) -> bool:
    """SQLAlchemy IntegrityError가 EXCLUDE GIST 제약 위반인지 식별."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == RESERVATION_OVERLAP_CONSTRAINT:
        return True
    # diag.constraint_name이 비어 있으면 메시지로도 한 번 확인(asyncpg 일부 버전 대비).
    message = str(orig or exc)
    return RESERVATION_OVERLAP_CONSTRAINT in message


async def get_active_reservation_for_host(
    db: AsyncSession, host_id: int, *, at_time: datetime
) -> Reservation | None:
    """T06 IN_USE 판정용 — 주어진 시각이 [starts_at, ends_at) 안인 CONFIRMED 예약 1건.

    호스트당 동시 활성은 0001의 EXCLUDE GIST 제약이 1건 이하로 강제하므로 limit(1) 안전.
    COMPLETED는 통상 종료 처리된 상태라 `time_range @> now`에는 매치되지 않는다.
    """
    stmt = (
        select(Reservation)
        .where(
            Reservation.host_id == host_id,
            Reservation.status == "CONFIRMED",
            text("time_range @> :at_time").bindparams(at_time=at_time),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# Helper for router — extract (starts_at, ends_at) from reservation.time_range.
def reservation_bounds(reservation: Reservation) -> tuple[datetime, datetime]:
    raw = reservation.time_range
    lower = getattr(raw, "lower", None)
    upper = getattr(raw, "upper", None)
    if lower is None or upper is None:
        raise RuntimeError(f"Reservation(id={reservation.id}).time_range 파싱 실패")
    if lower.tzinfo is None:
        lower = lower.replace(tzinfo=UTC)
    if upper.tzinfo is None:
        upper = upper.replace(tzinfo=UTC)
    return lower, upper
