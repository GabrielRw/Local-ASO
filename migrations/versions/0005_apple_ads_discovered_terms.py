"""Persist every search term returned by Apple Ads popularity reports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "apple_ads_discovered_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id"), nullable=False),
        sa.Column("search_term", sa.String(255), nullable=False),
        sa.Column("normalized_term", sa.String(255), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score >= 1 AND score <= 5", name="ck_discovered_term_score"),
        sa.UniqueConstraint(
            "app_id",
            "storefront_id",
            "normalized_term",
            name="uq_apple_ads_discovered_term",
        ),
    )
    for column in (
        "app_id",
        "storefront_id",
        "normalized_term",
        "score",
        "report_id",
    ):
        op.create_index(
            f"ix_apple_ads_discovered_terms_{column}",
            "apple_ads_discovered_terms",
            [column],
        )


def downgrade() -> None:
    op.drop_table("apple_ads_discovered_terms")
