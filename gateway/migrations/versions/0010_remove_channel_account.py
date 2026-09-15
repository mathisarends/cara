"""remove session channel account

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite refuses to drop a column that an index still covers.
    op.drop_index("ix_gateway_sessions_channel", table_name="gateway_sessions")
    op.drop_column("gateway_sessions", "channel_account_id")
    op.create_index(
        "ix_gateway_sessions_channel",
        "gateway_sessions",
        ["channel_name", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_gateway_sessions_channel", table_name="gateway_sessions")
    op.add_column(
        "gateway_sessions",
        sa.Column("channel_account_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_gateway_sessions_channel",
        "gateway_sessions",
        ["channel_name", "channel_account_id", "created_at"],
    )
