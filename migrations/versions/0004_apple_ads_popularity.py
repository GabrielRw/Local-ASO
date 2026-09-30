"""Store official Apple Ads search popularity and sync provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "keyword_popularities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id"), nullable=False),
        sa.Column("keyword_id", sa.Integer(), sa.ForeignKey("keywords.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="apple_ads"),
        sa.CheckConstraint("score >= 1 AND score <= 5", name="ck_keyword_popularity_score"),
        sa.UniqueConstraint("app_id", "keyword_id", "storefront_id", name="uq_keyword_popularity"),
    )
    for column in ("app_id", "keyword_id", "storefront_id", "report_id"):
        op.create_index(f"ix_keyword_popularities_{column}", "keyword_popularities", [column])

    op.create_table(
        "popularity_syncs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id"), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("report_start", sa.Date()),
        sa.Column("report_end", sa.Date()),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_keywords", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("report_id"),
    )
    for column in ("app_id", "storefront_id", "report_id", "state"):
        op.create_index(f"ix_popularity_syncs_{column}", "popularity_syncs", [column])


def downgrade() -> None:
    op.drop_table("popularity_syncs")
    op.drop_table("keyword_popularities")
