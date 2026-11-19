"""Remove retired popularity report data without changing rank tracking."""

from collections.abc import Sequence

from alembic import op
from alembic.script import ScriptDirectory

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("apple_ads_discovered_terms")
    op.drop_table("popularity_syncs")
    op.drop_table("keyword_popularities")


def downgrade() -> None:
    """Restore the historical schema, not previously removed report data."""

    scripts = ScriptDirectory.from_config(op.get_context().config)
    for revision_id in ("0004", "0005"):
        migration = scripts.get_revision(revision_id)
        if migration is None:
            raise RuntimeError(f"missing historical schema migration {revision_id}")
        migration.module.upgrade()
