from datetime import datetime
from typing import Any, Literal

import structlog
from broker.app.infra.db import Base
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

ActorKind = Literal["user", "system", "agent"]
AuditResult = Literal["success", "failure", "denied"]


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    auth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (
        Index("ix_audit_logs_occurred_at", "occurred_at"),
        Index("ix_audit_logs_actor_occurred", "actor_user_id", "occurred_at"),
        Index(
            "ix_audit_logs_target_occurred",
            "target_kind",
            "target_id",
            "occurred_at",
        ),
        Index("ix_audit_logs_action_occurred", "action", "occurred_at"),
    )


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: int | None,
    actor_kind: ActorKind = "user",
    target_kind: str | None = None,
    target_id: int | None = None,
    result: AuditResult = "success",
    detail: dict[str, Any] | None = None,
    request_id: str | None = None,
    auth_provider: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """감사 로그 작성 헬퍼.

    request_id는 명시되지 않으면 structlog contextvars에서 자동 픽업.
    호출자가 commit 책임을 지며, 본 함수는 add()만 수행.
    """
    if request_id is None:
        ctx = structlog.contextvars.get_contextvars()
        request_id = ctx.get("request_id")

    entry = AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
        target_kind=target_kind,
        target_id=target_id,
        result=result,
        detail=detail or {},
        request_id=request_id,
        auth_provider=auth_provider,
        ip_address=ip_address,
    )
    session.add(entry)
    return entry
