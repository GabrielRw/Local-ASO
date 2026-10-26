"""Add app-independent niche keyword research boards."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "niche_boards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "niche_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("niche_boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("normalized_keyword", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("board_id", "normalized_keyword", name="uq_niche_keyword"),
    )
    op.create_index("ix_niche_keywords_board_id", "niche_keywords", ["board_id"])
    op.create_index(
        "ix_niche_keywords_normalized_keyword",
        "niche_keywords",
        ["normalized_keyword"],
    )
    op.create_table(
        "niche_markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "board_id",
            sa.Integer(),
            sa.ForeignKey("niche_boards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("board_id", "country_code", name="uq_niche_market"),
    )
    op.create_index("ix_niche_markets_board_id", "niche_markets", ["board_id"])
    op.create_index("ix_niche_markets_country_code", "niche_markets", ["country_code"])
    op.create_table(
        "niche_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "niche_keyword_id",
            sa.Integer(),
            sa.ForeignKey("niche_keywords.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("volume_estimate", sa.Integer(), nullable=True),
        sa.Column("difficulty_estimate", sa.Integer(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "niche_keyword_id",
            "country_code",
            name="uq_niche_metric",
        ),
        sa.CheckConstraint(
            "volume_estimate IS NULL OR volume_estimate BETWEEN 0 AND 100",
            name="ck_niche_metrics_volume",
        ),
        sa.CheckConstraint(
            "difficulty_estimate IS NULL OR difficulty_estimate BETWEEN 0 AND 100",
            name="ck_niche_metrics_difficulty",
        ),
    )
    op.create_index(
        "ix_niche_metrics_niche_keyword_id",
        "niche_metrics",
        ["niche_keyword_id"],
    )
    op.create_index(
        "ix_niche_metrics_country_code",
        "niche_metrics",
        ["country_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_niche_metrics_country_code", table_name="niche_metrics")
    op.drop_index("ix_niche_metrics_niche_keyword_id", table_name="niche_metrics")
    op.drop_table("niche_metrics")
    op.drop_index("ix_niche_markets_country_code", table_name="niche_markets")
    op.drop_index("ix_niche_markets_board_id", table_name="niche_markets")
    op.drop_table("niche_markets")
    op.drop_index("ix_niche_keywords_normalized_keyword", table_name="niche_keywords")
    op.drop_index("ix_niche_keywords_board_id", table_name="niche_keywords")
    op.drop_table("niche_keywords")
    op.drop_table("niche_boards")
