"""Add persistent local app audits and keyword evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "app_id",
            sa.Integer(),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("prompt_version", sa.String(30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_runs_app_id", "audit_runs", ["app_id"])
    op.create_index("ix_audit_runs_status", "audit_runs", ["status"])
    op.create_index("ix_audit_runs_created_at", "audit_runs", ["created_at"])

    op.create_table(
        "audit_country_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "audit_run_id",
            sa.Integer(),
            sa.ForeignKey("audit_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("ranking_score", sa.Integer(), nullable=True),
        sa.Column("listing_score", sa.Integer(), nullable=True),
        sa.Column("localization_score", sa.Integer(), nullable=True),
        sa.Column("competition_score", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("audit_run_id", "country_code", name="uq_audit_country_result"),
    )
    op.create_index(
        "ix_audit_country_results_audit_run_id",
        "audit_country_results",
        ["audit_run_id"],
    )
    op.create_index(
        "ix_audit_country_results_country_code",
        "audit_country_results",
        ["country_code"],
    )

    op.create_table(
        "audit_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "audit_country_result_id",
            sa.Integer(),
            sa.ForeignKey("audit_country_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tone", sa.String(20), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("terms", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_audit_findings_audit_country_result_id",
        "audit_findings",
        ["audit_country_result_id"],
    )

    op.create_table(
        "audit_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "audit_country_result_id",
            sa.Integer(),
            sa.ForeignKey("audit_country_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("normalized_keyword", sa.String(255), nullable=False),
        sa.Column("intent", sa.String(255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("found", sa.Boolean(), nullable=True),
        sa.Column("result_limit", sa.Integer(), nullable=True),
        sa.Column("volume_estimate", sa.Integer(), nullable=True),
        sa.Column("difficulty_estimate", sa.Integer(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "audit_country_result_id",
            "normalized_keyword",
            name="uq_audit_keyword_country",
        ),
        sa.CheckConstraint(
            "volume_estimate IS NULL OR volume_estimate BETWEEN 0 AND 100",
            name="ck_audit_keywords_volume",
        ),
        sa.CheckConstraint(
            "difficulty_estimate IS NULL OR difficulty_estimate BETWEEN 0 AND 100",
            name="ck_audit_keywords_difficulty",
        ),
    )
    op.create_index(
        "ix_audit_keywords_audit_country_result_id",
        "audit_keywords",
        ["audit_country_result_id"],
    )
    op.create_index(
        "ix_audit_keywords_normalized_keyword",
        "audit_keywords",
        ["normalized_keyword"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_keywords_normalized_keyword", table_name="audit_keywords")
    op.drop_index("ix_audit_keywords_audit_country_result_id", table_name="audit_keywords")
    op.drop_table("audit_keywords")
    op.drop_index("ix_audit_findings_audit_country_result_id", table_name="audit_findings")
    op.drop_table("audit_findings")
    op.drop_index("ix_audit_country_results_country_code", table_name="audit_country_results")
    op.drop_index("ix_audit_country_results_audit_run_id", table_name="audit_country_results")
    op.drop_table("audit_country_results")
    op.drop_index("ix_audit_runs_created_at", table_name="audit_runs")
    op.drop_index("ix_audit_runs_status", table_name="audit_runs")
    op.drop_index("ix_audit_runs_app_id", table_name="audit_runs")
    op.drop_table("audit_runs")
