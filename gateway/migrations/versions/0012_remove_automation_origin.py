"""remove automation origin turn

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("gateway_automations", "created_from_turn_id")


def downgrade() -> None:
    # Rows created without an origin get the nil UUID.
    op.add_column(
        "gateway_automations",
        sa.Column(
            "created_from_turn_id",
            sa.Uuid(),
            nullable=False,
            server_default="00000000-0000-0000-0000-000000000000",
        ),
    )
