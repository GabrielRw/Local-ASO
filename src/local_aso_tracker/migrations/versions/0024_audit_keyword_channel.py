"""Separate competitor-brand searches (Apple Ads) from listing phrases in audits."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_keywords") as batch:
        batch.add_column(sa.Column("channel", sa.String(20), nullable=False, server_default="aso"))
        batch.add_column(sa.Column("brand_owner", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("audit_keywords") as batch:
        batch.drop_column("brand_owner")
        batch.drop_column("channel")
