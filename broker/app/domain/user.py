from broker.app.domain._mixins import IdMixin, TimestampMixin
from broker.app.infra.db import Base
from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_users_provider_external"),
        Index(
            "ix_users_role_admin",
            "role",
            postgresql_where="role = 'admin'",
        ),
    )
