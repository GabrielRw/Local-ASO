"""Store Apple Ads campaign country targeting."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "apple_ads_campaigns",
        sa.Column("countries", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("apple_ads_campaigns", "countries")
