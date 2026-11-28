"""Remember the storefronts Apple Ads does not serve."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "apple_ads_unsupported_markets",
        sa.Column("country_code", sa.String(2), primary_key=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("apple_ads_unsupported_markets")
