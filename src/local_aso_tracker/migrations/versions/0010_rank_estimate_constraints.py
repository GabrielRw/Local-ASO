"""Constrain ratings-derived estimate ranges."""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rank_estimates") as batch:
        batch.create_check_constraint(
            "ck_rank_estimates_volume",
            "volume IS NULL OR volume BETWEEN 0 AND 100",
        )
        batch.create_check_constraint(
            "ck_rank_estimates_difficulty",
            "difficulty IS NULL OR difficulty BETWEEN 0 AND 100",
        )
        batch.create_check_constraint(
            "ck_rank_estimates_sample_size",
            "sample_size BETWEEN 0 AND 10",
        )


def downgrade() -> None:
    with op.batch_alter_table("rank_estimates") as batch:
        batch.drop_constraint("ck_rank_estimates_sample_size", type_="check")
        batch.drop_constraint("ck_rank_estimates_difficulty", type_="check")
        batch.drop_constraint("ck_rank_estimates_volume", type_="check")
