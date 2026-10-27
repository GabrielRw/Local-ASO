"""Add persistent apps and ranks for the competitor keyword matrix."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_apps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("apple_app_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("artwork_url", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_competitor_apps_apple_app_id",
        "competitor_apps",
        ["apple_app_id"],
        unique=True,
    )
    op.create_index("ix_competitor_apps_active", "competitor_apps", ["active"])
    op.create_table(
        "competitor_ranks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "competitor_app_id",
            sa.Integer(),
            sa.ForeignKey("competitor_apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "keyword_id",
            sa.Integer(),
            sa.ForeignKey("keywords.id"),
            nullable=False,
        ),
        sa.Column(
            "storefront_id",
            sa.Integer(),
            sa.ForeignKey("storefronts.id"),
            nullable=False,
        ),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("result_limit", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "competitor_app_id",
            "keyword_id",
            "storefront_id",
            "device",
            name="uq_competitor_rank_target",
        ),
    )
    op.create_index(
        "ix_competitor_ranks_competitor_app_id",
        "competitor_ranks",
        ["competitor_app_id"],
    )
    op.create_index("ix_competitor_ranks_keyword_id", "competitor_ranks", ["keyword_id"])
    op.create_index("ix_competitor_ranks_storefront_id", "competitor_ranks", ["storefront_id"])
    op.create_index("ix_competitor_ranks_device", "competitor_ranks", ["device"])


def downgrade() -> None:
    op.drop_index("ix_competitor_ranks_device", table_name="competitor_ranks")
    op.drop_index("ix_competitor_ranks_storefront_id", table_name="competitor_ranks")
    op.drop_index("ix_competitor_ranks_keyword_id", table_name="competitor_ranks")
    op.drop_index("ix_competitor_ranks_competitor_app_id", table_name="competitor_ranks")
    op.drop_table("competitor_ranks")
    op.drop_index("ix_competitor_apps_active", table_name="competitor_apps")
    op.drop_index("ix_competitor_apps_apple_app_id", table_name="competitor_apps")
    op.drop_table("competitor_apps")
