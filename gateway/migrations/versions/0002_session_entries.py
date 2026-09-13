"""persist ordered session entries

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gateway_session_user_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gateway_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "position",
            name="uq_gateway_session_user_messages_session_position",
        ),
    )
    op.create_table(
        "gateway_session_assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gateway_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "position",
            name="uq_gateway_session_assistant_messages_session_position",
        ),
    )
    op.create_table(
        "gateway_session_tool_call_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gateway_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "position",
            name="uq_gateway_session_tool_call_sequences_session_position",
        ),
    )
    op.create_table(
        "gateway_session_tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(), nullable=False),
        sa.Column("function_name", sa.String(), nullable=False),
        sa.Column("function_arguments", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sequence_id"],
            ["gateway_session_tool_call_sequences.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sequence_id",
            "call_id",
            name="uq_gateway_session_tool_calls_sequence_call_id",
        ),
        sa.UniqueConstraint(
            "sequence_id",
            "position",
            name="uq_gateway_session_tool_calls_sequence_position",
        ),
    )
    op.create_index(
        "ix_gateway_session_tool_calls_call_id",
        "gateway_session_tool_calls",
        ["call_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gateway_session_tool_calls_call_id",
        table_name="gateway_session_tool_calls",
    )
    op.drop_table("gateway_session_tool_calls")
    op.drop_table("gateway_session_tool_call_sequences")
    op.drop_table("gateway_session_assistant_messages")
    op.drop_table("gateway_session_user_messages")
