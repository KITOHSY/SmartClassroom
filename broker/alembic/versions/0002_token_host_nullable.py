"""tokens.host_id nullable (auth session needs no host)

Revision ID: 0002_token_host_nullable
Revises: 0001_initial
Create Date: 2026-05-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_token_host_nullable"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("tokens", "host_id", nullable=True)


def downgrade() -> None:
    raise RuntimeError(
        "0002 downgrade is unsafe: rows with purpose='session' likely have host_id IS NULL. "
        "Delete them explicitly before attempting downgrade."
    )
