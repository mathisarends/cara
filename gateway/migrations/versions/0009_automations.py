"""persist automations

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gateway_automations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("target_kind", sa.String(), nullable=False),
        sa.Column("target_session_id", sa.Uuid(), nullable=True),
        sa.Column("schedule_kind", sa.String(), nullable=False),
        sa.Column("schedule_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule_every_seconds", sa.Float(), nullable=True),
        sa.Column("schedule_run_immediately", sa.Boolean(), nullable=True),
        sa.Column("schedule_cron_expression", sa.String(), nullable=True),
        sa.Column("schedule_cron_timezone", sa.String(), nullable=True),
        sa.Column("instruction", sa.String(), nullable=False),
        sa.Column("created_from_turn_id", sa.Uuid(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gateway_automations_owner_id",
        "gateway_automations",
        ["owner_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gateway_automations_owner_id",
        table_name="gateway_automations",
    )
    op.drop_table("gateway_automations")
