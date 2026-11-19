"""Add read-only Apple Ads reporting tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "apple_ads_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ad_account_id", sa.BigInteger(), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("roles", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_apple_ads_accounts_ad_account_id",
        "apple_ads_accounts",
        ["ad_account_id"],
        unique=True,
    )
    op.create_table(
        "apple_ads_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ad_account_id",
            sa.Integer(),
            sa.ForeignKey("apple_ads_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("promoted_object_id", sa.BigInteger(), nullable=True),
        sa.Column("promoted_object_type", sa.String(40), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ad_account_id", "campaign_id", name="uq_apple_ads_campaign"),
    )
    op.create_index(
        "ix_apple_ads_campaigns_ad_account_id",
        "apple_ads_campaigns",
        ["ad_account_id"],
    )
    op.create_index(
        "ix_apple_ads_campaigns_campaign_id",
        "apple_ads_campaigns",
        ["campaign_id"],
    )
    op.create_index(
        "ix_apple_ads_campaigns_promoted_object_id",
        "apple_ads_campaigns",
        ["promoted_object_id"],
    )
    op.create_table(
        "apple_ads_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("apple_ads_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword_id", sa.BigInteger(), nullable=False),
        sa.Column("ad_group_id", sa.BigInteger(), nullable=True),
        sa.Column("ad_group_name", sa.String(255), nullable=True),
        sa.Column("text", sa.String(255), nullable=False),
        sa.Column("normalized_text", sa.String(255), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("display_status", sa.String(30), nullable=True),
        sa.Column("bid_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("bid_currency", sa.String(3), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("campaign_id", "keyword_id", name="uq_apple_ads_keyword"),
    )
    op.create_index(
        "ix_apple_ads_keywords_campaign_id",
        "apple_ads_keywords",
        ["campaign_id"],
    )
    op.create_index(
        "ix_apple_ads_keywords_keyword_id",
        "apple_ads_keywords",
        ["keyword_id"],
    )
    op.create_index(
        "ix_apple_ads_keywords_normalized_text",
        "apple_ads_keywords",
        ["normalized_text"],
    )
    op.create_table(
        "apple_ads_keyword_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ad_account_id",
            sa.Integer(),
            sa.ForeignKey("apple_ads_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "apple_ads_keyword_id",
            sa.Integer(),
            sa.ForeignKey("apple_ads_keywords.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("country_or_region", sa.String(10), nullable=False),
        sa.Column("device_class", sa.String(20), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("taps", sa.Integer(), nullable=False),
        sa.Column("local_spend", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("tap_installs", sa.Integer(), nullable=False),
        sa.Column("total_installs", sa.Integer(), nullable=False),
        sa.Column("ttr", sa.Numeric(10, 6), nullable=True),
        sa.Column("cpt", sa.Numeric(14, 4), nullable=True),
        sa.Column("suggested_bid", sa.Numeric(14, 4), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "apple_ads_keyword_id",
            "metric_date",
            "country_or_region",
            "device_class",
            name="uq_apple_ads_keyword_metric",
        ),
    )
    op.create_index(
        "ix_apple_ads_keyword_metrics_ad_account_id",
        "apple_ads_keyword_metrics",
        ["ad_account_id"],
    )
    op.create_index(
        "ix_apple_ads_keyword_metrics_apple_ads_keyword_id",
        "apple_ads_keyword_metrics",
        ["apple_ads_keyword_id"],
    )
    op.create_index(
        "ix_apple_ads_keyword_metrics_metric_date",
        "apple_ads_keyword_metrics",
        ["metric_date"],
    )
    op.create_index(
        "ix_apple_ads_keyword_metrics_country_or_region",
        "apple_ads_keyword_metrics",
        ["country_or_region"],
    )
    op.create_index(
        "ix_apple_ads_keyword_metrics_device_class",
        "apple_ads_keyword_metrics",
        ["device_class"],
    )
    op.create_index(
        "ix_apple_ads_metrics_account_date",
        "apple_ads_keyword_metrics",
        ["ad_account_id", "metric_date"],
    )
    op.create_table(
        "apple_ads_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country_or_region", sa.String(10), nullable=False),
        sa.Column("text", sa.String(255), nullable=False),
        sa.Column("normalized_text", sa.String(255), nullable=False),
        sa.Column("popularity", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "app_id",
            "country_or_region",
            "normalized_text",
            name="uq_apple_ads_suggestion",
        ),
    )
    op.create_index(
        "ix_apple_ads_suggestions_app_id",
        "apple_ads_suggestions",
        ["app_id"],
    )
    op.create_index(
        "ix_apple_ads_suggestions_country_or_region",
        "apple_ads_suggestions",
        ["country_or_region"],
    )
    op.create_index(
        "ix_apple_ads_suggestions_normalized_text",
        "apple_ads_suggestions",
        ["normalized_text"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_apple_ads_suggestions_normalized_text",
        table_name="apple_ads_suggestions",
    )
    op.drop_index(
        "ix_apple_ads_suggestions_country_or_region",
        table_name="apple_ads_suggestions",
    )
    op.drop_index("ix_apple_ads_suggestions_app_id", table_name="apple_ads_suggestions")
    op.drop_table("apple_ads_suggestions")
    op.drop_index("ix_apple_ads_metrics_account_date", table_name="apple_ads_keyword_metrics")
    op.drop_index(
        "ix_apple_ads_keyword_metrics_device_class",
        table_name="apple_ads_keyword_metrics",
    )
    op.drop_index(
        "ix_apple_ads_keyword_metrics_country_or_region",
        table_name="apple_ads_keyword_metrics",
    )
    op.drop_index(
        "ix_apple_ads_keyword_metrics_metric_date",
        table_name="apple_ads_keyword_metrics",
    )
    op.drop_index(
        "ix_apple_ads_keyword_metrics_apple_ads_keyword_id",
        table_name="apple_ads_keyword_metrics",
    )
    op.drop_index(
        "ix_apple_ads_keyword_metrics_ad_account_id",
        table_name="apple_ads_keyword_metrics",
    )
    op.drop_table("apple_ads_keyword_metrics")
    op.drop_index("ix_apple_ads_keywords_normalized_text", table_name="apple_ads_keywords")
    op.drop_index("ix_apple_ads_keywords_keyword_id", table_name="apple_ads_keywords")
    op.drop_index("ix_apple_ads_keywords_campaign_id", table_name="apple_ads_keywords")
    op.drop_table("apple_ads_keywords")
    op.drop_index(
        "ix_apple_ads_campaigns_promoted_object_id",
        table_name="apple_ads_campaigns",
    )
    op.drop_index("ix_apple_ads_campaigns_campaign_id", table_name="apple_ads_campaigns")
    op.drop_index("ix_apple_ads_campaigns_ad_account_id", table_name="apple_ads_campaigns")
    op.drop_table("apple_ads_campaigns")
    op.drop_index(
        "ix_apple_ads_accounts_ad_account_id",
        table_name="apple_ads_accounts",
        unique=True,
    )
    op.drop_table("apple_ads_accounts")
