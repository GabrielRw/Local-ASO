"""Keep Apple Ads popularity with each audited keyword."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_keywords") as batch:
        batch.add_column(sa.Column("apple_popularity", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("popularity_status", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("audit_keywords") as batch:
        batch.drop_column("popularity_status")
        batch.drop_column("apple_popularity")
