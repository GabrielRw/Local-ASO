"""Keywords marked as a competitor's brand name, per app."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_brand_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("normalized_keyword", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_id", "normalized_keyword", name="uq_competitor_brand_keyword"),
    )
    op.create_index("ix_competitor_brand_keywords_app_id", "competitor_brand_keywords", ["app_id"])


def downgrade() -> None:
    op.drop_index("ix_competitor_brand_keywords_app_id", table_name="competitor_brand_keywords")
    op.drop_table("competitor_brand_keywords")
