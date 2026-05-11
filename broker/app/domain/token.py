from datetime import datetime

from broker.app.domain._mixins import IdMixin, TimestampMixin
from broker.app.infra.db import Base
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column


class Token(IdMixin, TimestampMixin, Base):
    __tablename__ = "tokens"

    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    host_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hosts.id"), nullable=False)
    reservation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reservations.id"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_tokens_user_expires", "user_id", "expires_at"),
        Index(
            "ix_tokens_active_expires",
            "expires_at",
            postgresql_where="consumed_at IS NULL AND revoked_at IS NULL",
        ),
    )
