"""add voice sessions and turns

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_encoding", sa.String(), nullable=False),
        sa.Column("input_sample_rate", sa.Integer(), nullable=False),
        sa.Column("input_channels", sa.Integer(), nullable=False),
        sa.Column("output_encoding", sa.String(), nullable=False),
        sa.Column("output_sample_rate", sa.Integer(), nullable=False),
        sa.Column("output_channels", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["gateway_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_voice_sessions_session_id",
        "voice_sessions",
        ["session_id"],
    )
    op.create_index(
        "ix_voice_sessions_device_id",
        "voice_sessions",
        ["device_id"],
    )
    op.create_index(
        "uq_voice_sessions_open_device",
        "voice_sessions",
        ["device_id"],
        unique=True,
        sqlite_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "voice_turns",
        sa.Column("voice_session_id", sa.Uuid(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("activation", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("transcript", sa.String(), nullable=True),
        sa.Column("user_message_id", sa.Uuid(), nullable=True),
        sa.Column("stt_provider", sa.String(), nullable=True),
        sa.Column("tts_provider", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("input_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("speech_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["voice_session_id"],
            ["voice_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["gateway_session_user_messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "voice_session_id",
            "index",
            name="uq_voice_turns_session_index",
        ),
    )
    op.create_index(
        "ix_voice_turns_user_message_id",
        "voice_turns",
        ["user_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_turns_user_message_id", table_name="voice_turns")
    op.drop_table("voice_turns")
    op.drop_index("uq_voice_sessions_open_device", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_device_id", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_session_id", table_name="voice_sessions")
    op.drop_table("voice_sessions")
