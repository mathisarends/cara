"""Guarantee one current conversation session per channel."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gateway_sessions",
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE gateway_sessions AS candidate
            SET is_current = true
            WHERE NOT EXISTS (
                SELECT 1
                FROM gateway_sessions AS newer
                WHERE newer.channel_name = candidate.channel_name
                  AND (
                    newer.created_at > candidate.created_at
                    OR (
                        newer.created_at = candidate.created_at
                        AND newer.id > candidate.id
                    )
                  )
            )
            """
        )
    )
    op.create_index(
        "uq_gateway_sessions_current_channel",
        "gateway_sessions",
        ["channel_name"],
        unique=True,
        sqlite_where=sa.text("is_current"),
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_gateway_sessions_current_channel",
        table_name="gateway_sessions",
    )
    op.drop_column("gateway_sessions", "is_current")
