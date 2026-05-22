"""T08 자동 페어링 API.

POST /pairing — 클라이언트(Moonlight, 배선은 향후 T14)가 connect 토큰 + 자신이 생성한
4자리 PIN을 넘기면, Broker가 connect 토큰을 검증하고 그 PIN을 예약 호스트의 Sunshine
`/api/pin`으로 중계한다. connect 토큰 자체가 인증 수단 — 사용자 세션/admin 불필요.

토큰은 verify만 하고 소비(consume)는 안 한다 — 1회 소비는 스트림 시작 시점.
실패는 dict-detail HTTPException + `fallback: manual_pin`(T19 수동 PIN 폴백 신호).
audit는 결과 1행만(`pairing_succeeded`/`pairing_failed`) — 재시도마다 남기지 않는다.
"""

from __future__ import annotations

from broker.app.api.deps import get_db
from broker.app.api.schemas.pairing import PairingRequest, PairingResponse
from broker.app.api.schemas.token import HostConnectionInfo
from broker.app.core.config import get_settings
from broker.app.domain.audit import write_audit
from broker.app.domain.host import Host
from broker.app.services import pairing_service, token_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _status_for(exc: pairing_service.PairingError) -> int:
    if isinstance(exc, pairing_service.HostNotPairableError):
        return status.HTTP_422_UNPROCESSABLE_ENTITY
    if isinstance(exc, pairing_service.PairingUnreachableError):
        return status.HTTP_502_BAD_GATEWAY
    return status.HTTP_409_CONFLICT  # PairingRejectedError


@router.post("", response_model=PairingResponse)
async def pairing_endpoint(
    payload: PairingRequest,
    db: AsyncSession = Depends(get_db),
) -> PairingResponse:
    token = await token_service.verify_connect_token(db, payload.token)
    if token is None or token.reservation_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_connect_token",
                "message": "connect 토큰이 유효하지 않습니다",
                "fallback": "manual_pin",
            },
        )

    host = await db.get(Host, token.host_id)
    if host is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "host_missing",
                "message": "토큰의 호스트가 존재하지 않습니다",
                "fallback": "manual_pin",
            },
        )

    settings = get_settings()
    try:
        result = await pairing_service.push_pin(
            host,
            payload.pin,
            reservation_id=token.reservation_id,
            settings=settings,
        )
    except pairing_service.PairingError as exc:
        await write_audit(
            db,
            action="pairing_failed",
            actor_user_id=token.user_id,
            actor_kind="user",
            target_kind="host",
            target_id=host.id,
            result="failure",
            detail={
                "reservation_id": token.reservation_id,
                "reason": exc.reason,
                "attempts": exc.attempts,
            },
        )
        await db.commit()
        raise HTTPException(
            status_code=_status_for(exc),
            detail={
                "error": exc.reason,
                "message": exc.message,
                "fallback": "manual_pin",
            },
        ) from exc

    await write_audit(
        db,
        action="pairing_succeeded",
        actor_user_id=token.user_id,
        actor_kind="user",
        target_kind="host",
        target_id=host.id,
        detail={"reservation_id": token.reservation_id, "attempts": result.attempts},
    )
    await db.commit()
    return PairingResponse(
        status="paired_pending",
        host=HostConnectionInfo.model_validate(host),
    )
