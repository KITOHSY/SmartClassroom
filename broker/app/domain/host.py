from datetime import datetime
from typing import Any

from broker.app.domain._mixins import IdMixin, TimestampMixin
from broker.app.infra.db import Base
from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column


class Host(IdMixin, TimestampMixin, Base):
    __tablename__ = "hosts"

    hostname: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    sunshine_port: Mapped[int] = mapped_column(Integer, nullable=False, default=47984)
    # Sunshine confighttp Bearer 토큰 (T08) — Broker가 /api/pin 등 머신 호출 시 제시.
    # sunshine.conf의 broker_api_token과 짝. 아웃바운드 시크릿이라 응답 스키마에는 미노출.
    sunshine_broker_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gpu_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OFFLINE")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    host_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (
        Index("ix_hosts_status", "status"),
        Index("ix_hosts_last_heartbeat", "last_heartbeat_at"),
    )
