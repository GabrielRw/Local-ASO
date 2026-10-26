"""Persist localized listing metadata used by coverage analysis."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "storefront_id",
            sa.Integer(),
            sa.ForeignKey("storefronts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subtitle", sa.String(255), nullable=False),
        sa.Column("keyword_field", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "app_id",
            "storefront_id",
            name="uq_listing_metadata_app_storefront",
        ),
    )
    op.create_index("ix_listing_metadata_app_id", "listing_metadata", ["app_id"])
    op.create_index(
        "ix_listing_metadata_storefront_id",
        "listing_metadata",
        ["storefront_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_metadata_storefront_id", table_name="listing_metadata")
    op.drop_index("ix_listing_metadata_app_id", table_name="listing_metadata")
    op.drop_table("listing_metadata")
