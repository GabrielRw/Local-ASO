"""Persist public artwork for every tracked app."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_artwork",
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("artwork_url", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_artwork")
