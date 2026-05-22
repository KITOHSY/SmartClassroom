"""hosts.sunshine_broker_token — Sunshine confighttp Bearer 토큰 (T08)

Revision ID: 0003_host_sunshine_broker_token
Revises: 0002_token_host_nullable
Create Date: 2026-05-22

Broker가 자동 페어링 시 Sunshine `/api/pin`을 호출할 때 제시하는 per-host Bearer
토큰. Sunshine `sunshine.conf`의 `broker_api_token`과 짝. nullable — 미등록 호스트는
페어링 불가(라우터가 host_not_pairable로 처리).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_host_sunshine_broker_token"
down_revision: str | None = "0002_token_host_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hosts",
        sa.Column("sunshine_broker_token", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hosts", "sunshine_broker_token")
