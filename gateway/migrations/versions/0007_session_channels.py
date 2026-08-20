"""persist session channel identity

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gateway_sessions",
        sa.Column(
            "channel_name",
            sa.String(),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "gateway_sessions",
        sa.Column("channel_account_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_gateway_sessions_channel",
        "gateway_sessions",
        [
            "channel_name",
            "channel_account_id",
            "created_at",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_gateway_sessions_channel", table_name="gateway_sessions")
    op.drop_column("gateway_sessions", "channel_account_id")
    op.drop_column("gateway_sessions", "channel_name")
