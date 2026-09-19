"""Remove obsolete session inactivity timeouts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("gateway_sessions", "inactivity_timeout_seconds")


def downgrade() -> None:
    op.add_column(
        "gateway_sessions",
        sa.Column("inactivity_timeout_seconds", sa.Float(), nullable=True),
    )
