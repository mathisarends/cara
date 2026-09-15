"""persist alarms

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gateway_alarms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("target_kind", sa.String(), nullable=False),
        sa.Column("target_session_id", sa.Uuid(), nullable=True),
        sa.Column("recurrence_kind", sa.String(), nullable=False),
        sa.Column("once_wake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weekly_days", sa.String(), nullable=True),
        sa.Column("weekly_local_time", sa.String(), nullable=True),
        sa.Column("weekly_timezone", sa.String(), nullable=True),
        sa.Column("routine_skill", sa.String(), nullable=False),
        sa.Column("routine_note", sa.String(), nullable=True),
        sa.Column("pre_wake_lead_seconds", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("skipped_dates", sa.String(), nullable=False),
        sa.Column("occurrence_wake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_state", sa.String(), nullable=True),
        sa.Column("occurrence_snooze_count", sa.Integer(), nullable=True),
        sa.Column(
            "occurrence_snoozed_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "occurrence_activated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gateway_alarms_owner_id", "gateway_alarms", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_gateway_alarms_owner_id", table_name="gateway_alarms")
    op.drop_table("gateway_alarms")
