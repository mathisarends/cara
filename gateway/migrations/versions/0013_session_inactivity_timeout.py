"""add session inactivity timeouts

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gateway_sessions",
        sa.Column("inactivity_timeout_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gateway_sessions", "inactivity_timeout_seconds")
