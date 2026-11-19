"""Store the localized phrase searched for each niche keyword per market."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "niche_keyword_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "niche_keyword_id",
            sa.Integer(),
            sa.ForeignKey("niche_keywords.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("term", sa.String(255), nullable=False),
        sa.Column("language", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("niche_keyword_id", "country_code", name="uq_niche_keyword_term"),
    )
    op.create_index(
        "ix_niche_keyword_terms_niche_keyword_id", "niche_keyword_terms", ["niche_keyword_id"]
    )
    op.create_index("ix_niche_keyword_terms_country_code", "niche_keyword_terms", ["country_code"])


def downgrade() -> None:
    op.drop_index("ix_niche_keyword_terms_country_code", table_name="niche_keyword_terms")
    op.drop_index("ix_niche_keyword_terms_niche_keyword_id", table_name="niche_keyword_terms")
    op.drop_table("niche_keyword_terms")
