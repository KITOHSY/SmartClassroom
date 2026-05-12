"""T07 토큰 검증 API.

POST /tokens/verify — Broker 내부 호출용. T08 자동 페어링 + T10 Sunshine fork가 호출자.

T07 시점 보호: `Depends(require_admin)` (임시).
TODO(T08): X-Internal-Token 헤더 또는 mTLS 기반 internal auth로 교체 — §11 A6.

응답 정책: 200 OK + `valid: bool` 모델 — HTTPException 안 씀.
호출자가 valid 플래그로 분기하기 쉽게 (T10 Sunshine fork가 단순 JSON 파싱 가능).
"""

from __future__ import annotations

from broker.app.api.deps import get_db, require_admin
from broker.app.api.schemas.token import TokenVerifyRequest, TokenVerifyResponse
from broker.app.domain.audit import write_audit
from broker.app.domain.user import User
from broker.app.services import token_service
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/verify", response_model=TokenVerifyResponse)
async def verify_token_endpoint(
    payload: TokenVerifyRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),  # TODO(T08): internal auth 교체 (§11 A6)
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
