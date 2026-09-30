"""Store private listing metadata used by the local ASO principle audit."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_metadata_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("app_id", sa.Integer(), sa.ForeignKey("apps.id"), nullable=False),
        sa.Column("storefront_id", sa.Integer(), sa.ForeignKey("storefronts.id"), nullable=False),
        sa.Column("subtitle", sa.String(30), nullable=False, server_default=""),
        sa.Column("keywords_field", sa.String(100), nullable=False, server_default=""),
        sa.Column("brand_term", sa.String(30), nullable=False, server_default=""),
        sa.Column("distribution_strategy", sa.String(20), nullable=False, server_default="organic"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_id", "storefront_id", name="uq_listing_metadata_audit"),
    )
    op.create_index("ix_listing_metadata_audits_app_id", "listing_metadata_audits", ["app_id"])
    op.create_index(
        "ix_listing_metadata_audits_storefront_id",
        "listing_metadata_audits",
        ["storefront_id"],
    )


def downgrade() -> None:
    op.drop_table("listing_metadata_audits")
