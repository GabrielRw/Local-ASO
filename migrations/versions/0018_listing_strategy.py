"""Store listing distribution goal and brand term."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing_metadata",
        sa.Column(
            "channel_goal",
            sa.String(30),
            nullable=False,
            server_default="aso_seo_aeo",
        ),
    )
    op.add_column(
        "listing_metadata",
        sa.Column("brand_term", sa.String(255), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("listing_metadata", "brand_term")
    op.drop_column("listing_metadata", "channel_goal")
