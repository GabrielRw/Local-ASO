"""Store Apple Ads popularity per keyword and market.

Suggestion popularity saved before this revision was taken from other seeds'
suggestion lists, which Apple scores relative to that seed, so it is cleared.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "keyword_popularity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("normalized_keyword", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("popularity", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("normalized_keyword", "country_code", name="uq_keyword_popularity"),
        sa.CheckConstraint(
            "popularity IS NULL OR popularity BETWEEN 0 AND 100",
            name="ck_keyword_popularity_range",
        ),
    )
    op.create_index(
        "ix_keyword_popularity_normalized_keyword",
        "keyword_popularity",
        ["normalized_keyword"],
    )
    op.create_index("ix_keyword_popularity_country_code", "keyword_popularity", ["country_code"])
    op.execute("UPDATE apple_ads_suggestions SET popularity = NULL")


def downgrade() -> None:
    op.drop_index("ix_keyword_popularity_country_code", table_name="keyword_popularity")
    op.drop_index("ix_keyword_popularity_normalized_keyword", table_name="keyword_popularity")
    op.drop_table("keyword_popularity")
