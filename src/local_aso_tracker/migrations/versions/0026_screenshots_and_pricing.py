"""Screenshot studio (sources, captions, renders, push log) and price push log."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _app_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "app_id", sa.Integer(), sa.ForeignKey("apps.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
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
    op.create_table(
        "price_push_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        _app_fk(),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("territory", sa.String(3), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("before_price", sa.String(32), nullable=True),
        sa.Column("after_price", sa.String(32), nullable=False),
        sa.Column("after_price_point", sa.String(128), nullable=False),
        sa.Column("start_date", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_push_events_app_id", "price_push_events", ["app_id"])


def downgrade() -> None:
    for table in (
        "price_push_events",
        "screenshot_push_events",
        "screenshot_renders",
        "screenshot_captions",
        "screenshot_sources",
        "screenshot_settings",
    ):
        op.drop_table(table)
