"""initial schema (users, hosts, reservations, sessions, tokens, audit_logs)

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 필수 PG 확장.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("provider", "external_id", name="uq_users_provider_external"),
    )
    op.create_index(
        "ix_users_role_admin",
        "users",
        ["role"],
        postgresql_where=sa.text("role = 'admin'"),
    )

    # hosts
    op.create_table(
        "hosts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("hostname", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("location", sa.String(128), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("sunshine_port", sa.Integer, nullable=False, server_default="47984"),
        sa.Column("gpu_model", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="OFFLINE"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_hosts_status", "hosts", ["status"])
    op.create_index("ix_hosts_last_heartbeat", "hosts", ["last_heartbeat_at"])

    # reservations (EXCLUDE GIST 제약 — autogenerate가 못 잡으므로 raw SQL).
    op.create_table(
        "reservations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "host_id",
            sa.BigInteger,
            sa.ForeignKey("hosts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("time_range", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="CONFIRMED"),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        ALTER TABLE reservations ADD CONSTRAINT reservations_no_overlap
        EXCLUDE USING GIST (
            host_id WITH =,
            time_range WITH &&
        ) WHERE (status IN ('CONFIRMED', 'COMPLETED'))
        """
    )
    op.create_index(
        "ix_reservations_user_time",
        "reservations",
        ["user_id", "time_range"],
    )
    op.create_index(
        "ix_reservations_time_range_gist",
        "reservations",
        ["time_range"],
        postgresql_using="gist",
    )

    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "reservation_id",
            sa.BigInteger,
            sa.ForeignKey("reservations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "host_id",
            sa.BigInteger,
            sa.ForeignKey("hosts.id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(32), nullable=True),
        sa.Column(
            "client_info",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_sessions_reservation", "sessions", ["reservation_id"])
    op.create_index(
        "ix_sessions_active",
        "sessions",
        ["state"],
        postgresql_where=sa.text("state IN ('PENDING','PAIRING','ACTIVE')"),
    )
    op.create_index("ix_sessions_host_state", "sessions", ["host_id", "state"])

    # tokens
    op.create_table(
        "tokens",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("jti", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "host_id",
            sa.BigInteger,
            sa.ForeignKey("hosts.id"),
            nullable=False,
        ),
        sa.Column(
            "reservation_id",
            sa.BigInteger,
            sa.ForeignKey("reservations.id"),
            nullable=True,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_tokens_user_expires", "tokens", ["user_id", "expires_at"])
    op.create_index(
        "ix_tokens_active_expires",
        "tokens",
        ["expires_at"],
        postgresql_where=sa.text("consumed_at IS NULL AND revoked_at IS NULL"),
    )

    # audit_logs (public_id 없음 — 외부 노출 X)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actor_user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=True),
        sa.Column("target_id", sa.BigInteger, nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("auth_provider", sa.String(32), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])
    op.create_index(
        "ix_audit_logs_actor_occurred",
        "audit_logs",
        ["actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_logs_target_occurred",
        "audit_logs",
        ["target_kind", "target_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_logs_action_occurred",
        "audit_logs",
        ["action", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("tokens")
    op.drop_table("sessions")
    op.drop_table("reservations")
    op.drop_table("hosts")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
    # pgcrypto는 DB 전반에서 쓰일 수 있으므로 drop하지 않음.
