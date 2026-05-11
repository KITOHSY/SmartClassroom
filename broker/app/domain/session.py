from datetime import datetime
from typing import Any

from broker.app.domain._mixins import IdMixin, TimestampMixin
from broker.app.infra.db import Base
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class Session(IdMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    reservation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("reservations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    host_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hosts.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_info: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (
        Index("ix_sessions_reservation", "reservation_id"),
        Index(
            "ix_sessions_active",
            "state",
            postgresql_where="state IN ('PENDING','PAIRING','ACTIVE')",
        ),
        Index("ix_sessions_host_state", "host_id", "state"),
    )
