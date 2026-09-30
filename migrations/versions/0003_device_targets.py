"""Track iPhone and iPad keyword rankings independently."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tracking_targets") as batch:
        batch.add_column(
            sa.Column("device", sa.String(10), nullable=False, server_default="iphone")
        )
        batch.drop_constraint("uq_tracking_target", type_="unique")
        batch.create_unique_constraint(
            "uq_tracking_target", ["app_id", "keyword_id", "storefront_id", "device"]
        )
        batch.create_index("ix_tracking_targets_device", ["device"])


def downgrade() -> None:
    with op.batch_alter_table("tracking_targets") as batch:
        batch.drop_index("ix_tracking_targets_device")
        batch.drop_constraint("uq_tracking_target", type_="unique")
        batch.create_unique_constraint(
            "uq_tracking_target", ["app_id", "keyword_id", "storefront_id"]
        )
        batch.drop_column("device")
