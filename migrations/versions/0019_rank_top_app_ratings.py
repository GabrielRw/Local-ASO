"""Store ratings and rating counts for Top 5 search results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rank_top_apps",
        sa.Column("average_rating", sa.Float(), nullable=True),
    )
    op.add_column(
        "rank_top_apps",
        sa.Column("rating_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rank_top_apps", "rating_count")
    op.drop_column("rank_top_apps", "average_rating")
