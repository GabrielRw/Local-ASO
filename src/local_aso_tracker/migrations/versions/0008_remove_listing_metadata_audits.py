"""Remove the retired ASO principle audit without changing rank data."""

from collections.abc import Sequence

from alembic import op
from alembic.script import ScriptDirectory

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("listing_metadata_audits")


def downgrade() -> None:
    """Restore the historical schema, not removed private metadata."""

    scripts = ScriptDirectory.from_config(op.get_context().config)
    migration = scripts.get_revision("0002")
    if migration is None:
        raise RuntimeError("missing historical schema migration 0002")
    migration.module.upgrade()
