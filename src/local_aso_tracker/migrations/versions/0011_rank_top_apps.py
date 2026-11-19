"""Persist the first five search results shown with each rank check."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rank_top_apps",
        sa.Column(
            "rank_check_id",
            sa.Integer(),
            sa.ForeignKey("rank_checks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("artwork_url", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "position BETWEEN 1 AND 5",
            name="ck_rank_top_apps_position",
        ),
    )


def downgrade() -> None:
    op.drop_table("rank_top_apps")
