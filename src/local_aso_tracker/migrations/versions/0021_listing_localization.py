"""Add localized listing drafts, review iterations, and push history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_localization_settings",
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("main_country", sa.String(2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "listing_localization_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_country", sa.String(2), nullable=False),
        sa.Column("source_locale", sa.String(20), nullable=False),
        sa.Column("target_locale", sa.String(20), nullable=False),
        sa.Column("target_countries", sa.Text(), nullable=False),
        sa.Column("language", sa.String(60), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("source_fields", sa.Text(), nullable=False),
        sa.Column("fields", sa.Text(), nullable=False),
        sa.Column("validation", sa.Text(), nullable=False),
        sa.Column("remote_app_info_localization_id", sa.String(100), nullable=True),
        sa.Column("remote_version_localization_id", sa.String(100), nullable=True),
        sa.Column("remote_version_id", sa.String(100), nullable=True),
        sa.Column("remote_version_state", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("app_id", "target_locale", name="uq_listing_localization_locale"),
    )
    op.create_index(
        "ix_listing_localization_drafts_app_id",
        "listing_localization_drafts",
        ["app_id"],
    )
    op.create_index(
        "ix_listing_localization_drafts_target_locale",
        "listing_localization_drafts",
        ["target_locale"],
    )
    op.create_index(
        "ix_listing_localization_drafts_status",
        "listing_localization_drafts",
        ["status"],
    )

    op.create_table(
        "listing_localization_iterations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "draft_id",
            sa.Integer(),
            sa.ForeignKey("listing_localization_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("fields", sa.Text(), nullable=False),
        sa.Column("validation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("draft_id", "iteration", name="uq_listing_localization_iteration"),
    )
    op.create_index(
        "ix_listing_localization_iterations_draft_id",
        "listing_localization_iterations",
        ["draft_id"],
    )

    op.create_table(
        "listing_push_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "draft_id",
            sa.Integer(),
            sa.ForeignKey("listing_localization_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("fields", sa.Text(), nullable=False),
        sa.Column("before_values", sa.Text(), nullable=False),
        sa.Column("after_values", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_listing_push_events_draft_id",
        "listing_push_events",
        ["draft_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_push_events_draft_id", table_name="listing_push_events")
    op.drop_table("listing_push_events")
    op.drop_index(
        "ix_listing_localization_iterations_draft_id",
        table_name="listing_localization_iterations",
    )
    op.drop_table("listing_localization_iterations")
    op.drop_index(
        "ix_listing_localization_drafts_status",
        table_name="listing_localization_drafts",
    )
    op.drop_index(
        "ix_listing_localization_drafts_target_locale",
        table_name="listing_localization_drafts",
    )
    op.drop_index(
        "ix_listing_localization_drafts_app_id",
        table_name="listing_localization_drafts",
    )
    op.drop_table("listing_localization_drafts")
    op.drop_table("listing_localization_settings")
