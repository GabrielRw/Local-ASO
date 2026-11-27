"""Remove the screenshot studio: drop its tables (the price push log stays)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCREENSHOT_TABLES = (
    "screenshot_push_events",
    "screenshot_renders",
    "screenshot_captions",
    "screenshot_sources",
    "screenshot_settings",
)


def _app_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in SCREENSHOT_TABLES:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    op.create_table(
        "screenshot_settings",
        sa.Column(
            "app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("main_locale", sa.String(20), nullable=False),
        sa.Column("style", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "screenshot_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        _app_fk(),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(80), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_screenshot_sources_app_id", "screenshot_sources", ["app_id"])
    op.create_table(
        "screenshot_captions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("screenshot_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale", sa.String(20), nullable=False),
        sa.Column("headline", sa.String(120), nullable=False),
        sa.Column("subline", sa.String(200), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "locale", name="uq_screenshot_caption"),
    )
    op.create_index("ix_screenshot_captions_source_id", "screenshot_captions", ["source_id"])
    op.create_index("ix_screenshot_captions_locale", "screenshot_captions", ["locale"])
    op.create_table(
        "screenshot_renders",
        sa.Column("id", sa.Integer(), primary_key=True),
        _app_fk(),
        sa.Column("locale", sa.String(20), nullable=False),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(32), nullable=False),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_id", "locale", "device", "position", name="uq_screenshot_render"),
    )
    op.create_index("ix_screenshot_renders_app_id", "screenshot_renders", ["app_id"])
    op.create_index("ix_screenshot_renders_locale", "screenshot_renders", ["locale"])
    op.create_table(
        "screenshot_push_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        _app_fk(),
        sa.Column("locale", sa.String(20), nullable=False),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("before_ids", sa.Text(), nullable=False),
        sa.Column("after_ids", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_screenshot_push_events_app_id", "screenshot_push_events", ["app_id"])
