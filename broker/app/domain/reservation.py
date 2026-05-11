from datetime import datetime

from broker.app.domain._mixins import IdMixin, TimestampMixin
from broker.app.infra.db import Base
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import Mapped, mapped_column


class Reservation(IdMixin, TimestampMixin, Base):
    __tablename__ = "reservations"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    host_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("hosts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    time_range: Mapped[object] = mapped_column(TSTZRANGE, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CONFIRMED")
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # EXCLUDE USING GIST 제약은 ORM이 표현하기 까다로워서 0001 마이그레이션에서 raw SQL로 추가.
    __table_args__ = (
        Index("ix_reservations_user_time", "user_id", "time_range"),
        Index(
            "ix_reservations_time_range_gist",
            "time_range",
            postgresql_using="gist",
        ),
    )
