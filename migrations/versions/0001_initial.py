"""Initial Local ASO Tracker schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "apps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("apple_app_id", sa.Integer(), nullable=False),
        sa.Column("bundle_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("apple_app_id"),
    )
    op.create_index("ix_apps_apple_app_id", "apps", ["apple_app_id"])
    op.create_index("ix_apps_active", "apps", ["active"])
    op.create_table(
        "storefronts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("country_code"),
    )
    op.create_index("ix_storefronts_country_code", "storefronts", ["country_code"])
    op.create_index("ix_storefronts_active", "storefronts", ["active"])
    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("normalized_keyword", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("normalized_keyword"),
    )
    op.create_index("ix_keywords_normalized_keyword", "keywords", ["normalized_keyword"])
    op.create_index("ix_keywords_active", "keywords", ["active"])
    op.create_table(
        "tracking_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id"), nullable=False),
        sa.Column("keyword_id", sa.Integer(), sa.ForeignKey("keywords.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_id", "keyword_id", "storefront_id", name="uq_tracking_target"),
    )
    for column in ("app_id", "keyword_id", "storefront_id", "active"):
        op.create_index(f"ix_tracking_targets_{column}", "tracking_targets", [column])
    op.create_table(
        "rank_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tracking_target_id", sa.Integer(), sa.ForeignKey("tracking_targets.id"), nullable=False
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rank", sa.Integer()),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("result_limit", sa.Integer(), nullable=False),
        sa.Column("total_results_reported", sa.Integer()),
        sa.Column("app_name_returned", sa.String(255)),
        sa.Column("app_version_returned", sa.String(100)),
        sa.Column("app_store_url", sa.Text()),
        sa.Column("raw_response_hash", sa.String(64)),
        sa.Column("response_time_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_rank_checks_checked_at", "rank_checks", ["checked_at"])
    op.create_index("ix_rank_checks_status", "rank_checks", ["status"])
    op.create_index(
        "ix_rank_checks_target_checked", "rank_checks", ["tracking_target_id", "checked_at"]
    )


def downgrade() -> None:
    op.drop_table("rank_checks")
    op.drop_table("tracking_targets")
    op.drop_table("keywords")
    op.drop_table("storefronts")
    op.drop_table("apps")
