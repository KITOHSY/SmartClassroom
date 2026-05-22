"""T07 토큰 검증 API.

POST /tokens/verify — Broker 내부 호출용. T08 자동 페어링 + T10 Sunshine fork가 호출자.

보호: `Depends(require_internal_token)` — X-Internal-Token 헤더 공유 비밀 (§11 A6).
T08에서 T07 시점의 임시 가드 `require_admin`을 대체. 내부 컴포넌트는 사용자/admin
세션이 없는 머신이므로 별도 인증 채널을 쓴다.

응답 정책: 200 OK + `valid: bool` 모델 — 검증 결과는 HTTPException으로 분기 안 함
(인증 실패만 401). 호출자가 valid 플래그로 단순 분기 (T10 Sunshine fork가 JSON 파싱).
"""

from __future__ import annotations

from broker.app.api.deps import get_db, require_internal_token
from broker.app.api.schemas.token import TokenVerifyRequest, TokenVerifyResponse
from broker.app.domain.audit import write_audit
from broker.app.services import token_service
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/verify", response_model=TokenVerifyResponse)
async def verify_token_endpoint(
    payload: TokenVerifyRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_token),
) -> TokenVerifyResponse:
    token = await token_service.verify_connect_token(db, payload.token)
    if token is None:
        await write_audit(
            db,
            action="token_verify_failure",
            actor_user_id=None,
            actor_kind="system",
            target_kind="token",
            target_id=None,
            detail={"reason": "invalid_or_expired"},
        )
        await db.commit()
        return TokenVerifyResponse(valid=False, reason="invalid_or_expired")

    if payload.consume:
        consumed = await token_service.mark_consumed(db, token)
        if not consumed:
            # race — 다른 호출이 먼저 소비.
            await write_audit(
                db,
                action="token_verify_failure",
                actor_user_id=None,
                actor_kind="system",
                target_kind="token",
                target_id=token.id,
                detail={"reason": "already_consumed"},
            )
            await db.commit()
            return TokenVerifyResponse(valid=False, reason="already_consumed")

        await write_audit(
            db,
            action="token_consume",
            actor_user_id=None,
            actor_kind="system",
            target_kind="token",
            target_id=token.id,
            detail={
                "reservation_id": token.reservation_id,
                "user_id": token.user_id,
            },
        )
    else:
        await write_audit(
            db,
            action="token_verify",
            actor_user_id=None,
            actor_kind="system",
            target_kind="token",
            target_id=token.id,
            detail={
                "reservation_id": token.reservation_id,
                "user_id": token.user_id,
            },
        )

    await db.commit()
    return TokenVerifyResponse(
        valid=True,
        user_id=token.user_id,
        host_id=token.host_id,
        reservation_id=token.reservation_id,
        expires_at=token.expires_at,
    )
