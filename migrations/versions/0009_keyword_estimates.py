"""Add transparent ratings-based keyword estimates to rank checks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rank_estimates",
        sa.Column(
            "rank_check_id",
            sa.Integer(),
            sa.ForeignKey("rank_checks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rank_estimates")
