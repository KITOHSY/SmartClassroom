"""호스트 메타 API.

- GET /             — 인증된 사용자가 호스트 목록(메타데이터) 조회 (T16 부분 선행)
- POST /            — admin이 호스트 등록 + agent token 1회 발급 (T11 enrollment)
- POST /{id}/agent-token — admin이 agent token 재발급(이전 일괄 revoke) (T11)

T06 본구현 시 다음이 추가/흡수된다:
- POST /agents/heartbeat (ingest) — 본 라우터가 아니라 api/v1/agents.py
- GET /hosts/available (상태 필터)
- WebSocket/SSE 실시간 푸시

내부 호출 API 메모: heartbeat ingest(`api/v1/agents.py`)는 Bearer agent token 인증을 쓰며,
본 admin enrollment는 admin 사용자 액션이라 그대로 `require_admin` 유지.
"""

from __future__ import annotations

from datetime import datetime

from broker.app.api.deps import get_current_user, get_db, require_admin
from broker.app.api.schemas.host import (
    HostAvailable,
    HostCreate,
    HostRead,
    HostSunshineTokenUpdate,
    HostWithAgentToken,
)
from broker.app.core.errors import InvalidReservationWindowError
from broker.app.domain.host import Host
from broker.app.domain.user import User
from broker.app.services import reservation as reservation_service
from broker.app.services.agent_token_service import issue_agent_token
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _to_with_token(host: Host, raw_token: str, revoked_previous: int) -> HostWithAgentToken:
    return HostWithAgentToken.model_validate(
        {
            "id": host.id,
            "hostname": host.hostname,
            "display_name": host.display_name,
            "location": host.location,
            "status": host.status,
            "sunshine_port": host.sunshine_port,
            "agent_token": raw_token,
            "revoked_previous": revoked_previous,
        }
    )


@router.get("", response_model=list[HostRead])
async def list_hosts_endpoint(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[HostRead]:
    """호스트 목록을 id 오름차순으로 반환.

    인증 필수(미인증 401). admin/user 모두 동일 페이로드 — 호스트 메타는 학내 정보로 비공개.
    """
    result = await db.execute(select(Host).order_by(Host.id))
    hosts = result.scalars().all()
    return [HostRead.model_validate(h) for h in hosts]


def _ensure_grid_aligned(dt: datetime, slot_minutes: int = 30) -> None:
    """T05 _is_grid_aligned와 동일 패턴 — 30분 그리드 + tz-aware 강제."""
    if dt.tzinfo is None:
        raise InvalidReservationWindowError("from_/to_는 timezone-aware여야 합니다")
    if not (dt.minute % slot_minutes == 0 and dt.second == 0 and dt.microsecond == 0):
        raise InvalidReservationWindowError(
            f"from_/to_는 {slot_minutes}분 그리드에 정렬되어야 합니다",
            detail={"slot_minutes": slot_minutes},
        )


@router.get("/available", response_model=list[HostAvailable])
async def list_available_hosts_endpoint(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
) -> list[HostAvailable]:
    """T06/T17 — '접속 가능' 호스트 목록(`status='IDLE'`).

    파라미터 없이 호출하면(T17 바로 접속) 현재 예약이 없는 IDLE 호스트와 각 호스트의
    `available_until`(지금부터 즉시 사용 가능한 종료 시각 = min(다음 예약, 2.5h))을 반환.
    옵션 `?from=&to=` (반열림 `[from, to)`, 30분 그리드)이 함께 오면 해당 슬롯에
    활성 CONFIRMED 예약이 있는 호스트만 제외하는 슬롯 모드. 둘 중 하나만 오면 422.
    """
    if (from_ is None) != (to is None):
        raise InvalidReservationWindowError(
            "from_과 to는 함께 지정해야 합니다",
            detail={"from": from_, "to": to},
        )

    if from_ is not None and to is not None:
        # 슬롯 모드 — [from, to)에 활성 CONFIRMED 예약이 없는 IDLE 호스트.
        _ensure_grid_aligned(from_)
        _ensure_grid_aligned(to)
        if from_ >= to:
            raise InvalidReservationWindowError("from_은 to보다 이전이어야 합니다")
        stmt = (
            select(Host)
            .where(
                Host.status == "IDLE",
                text(
                    "NOT EXISTS (SELECT 1 FROM reservations r "
                    "WHERE r.host_id = hosts.id AND r.status='CONFIRMED' "
                    "AND r.time_range && tstzrange(:from_, :to_, '[)'))"
                ).bindparams(from_=from_, to_=to),
            )
            .order_by(Host.id)
        )
        result = await db.execute(stmt)
        return [HostAvailable.model_validate(h) for h in result.scalars().all()]

    # 파라미터 없음 — T17 바로 접속(현재 예약 없는 IDLE 호스트 + available_until).
    rows = await reservation_service.list_instant_available_hosts(db)
    return [
        HostAvailable(
            id=host.id,
            hostname=host.hostname,
            display_name=host.display_name,
            location=host.location,
            last_heartbeat_at=host.last_heartbeat_at,
            ip_address=host.ip_address,
            available_until=available_until,
        )
        for host, available_until in rows
    ]


@router.post(
    "",
    response_model=HostWithAgentToken,
    status_code=status.HTTP_201_CREATED,
)
async def create_host_endpoint(
    payload: HostCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> HostWithAgentToken:
    """관리자가 호스트를 등록하고 agent token을 1회 발급받는다.

    응답의 `agent_token`은 서버에 저장되지 않은 raw 값 — 인스톨러 config에 주입 후 분실 시 재발급.
    hostname UNIQUE 위반은 409로 변환.
    """
    host = Host(
        hostname=payload.hostname,
        display_name=payload.display_name,
        location=payload.location,
        ip_address=payload.ip_address,
        sunshine_port=payload.sunshine_port,
        sunshine_broker_token=payload.sunshine_broker_token,
        gpu_model=payload.gpu_model,
    )
    db.add(host)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        if "hosts_hostname_key" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "hostname_conflict", "hostname": payload.hostname},
            ) from e
        raise

    raw_token, _, revoked = await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()
    await db.refresh(host)
    return _to_with_token(host, raw_token, revoked)


@router.post("/{host_id}/agent-token", response_model=HostWithAgentToken)
async def rotate_agent_token_endpoint(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> HostWithAgentToken:
    """기존 agent token을 일괄 revoke 후 새 토큰 발급. 응답에 raw 1회 노출.

    호스트 미존재 시 404.
    """
    host = await db.get(Host, host_id)
    if host is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "host_not_found", "host_id": host_id},
        )
    raw_token, _, revoked = await issue_agent_token(db, host=host, issued_by=admin)
    await db.commit()
    return _to_with_token(host, raw_token, revoked)


@router.put("/{host_id}/sunshine-token", response_model=HostRead)
async def set_sunshine_token_endpoint(
    host_id: int,
    payload: HostSunshineTokenUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> HostRead:
    """T08 — 기존 호스트에 Sunshine 페어링 토큰(`broker_api_token`)을 등록/회전.

    응답(HostRead)에는 토큰을 노출하지 않는다 — 아웃바운드 시크릿. 호스트 미존재 시 404.
    """
    host = await db.get(Host, host_id)
    if host is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "host_not_found", "host_id": host_id},
        )
    host.sunshine_broker_token = payload.sunshine_broker_token
    await db.commit()
    await db.refresh(host)
    return HostRead.model_validate(host)
