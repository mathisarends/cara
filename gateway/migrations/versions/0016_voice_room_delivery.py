"""Add optional voice room delivery targets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gateway_automations",
        sa.Column("delivery_voice_room", sa.String(), nullable=True),
    )
    op.add_column(
        "gateway_alarms",
        sa.Column("delivery_voice_room", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gateway_alarms", "delivery_voice_room")
    op.drop_column("gateway_automations", "delivery_voice_room")
