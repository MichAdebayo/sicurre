"""Add generation run lineage tables.

Revision ID: 20260408_0002
Revises: 20260306_0001
Create Date: 2026-04-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0002"
down_revision = "20260306_0001"
branch_labels = None
depends_on = None


STATUS_CHECK = "status IN ('pending', 'running', 'completed', 'failed', 'partial')"
TARGET_LABEL_CHECK = "target_label IN ('phishing', 'spam', 'legitimate', 'unknown')"
REVIEW_STATE_CHECK = "review_state IN ('usable', 'needs_prompt_tuning', 'drop')"


def upgrade() -> None:
    op.create_table(
        "data_generation_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generator_name", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("parent_source", sa.Text(), nullable=True),
        sa.Column("reference_selection_mode", sa.Text(), nullable=True),
        sa.Column("input_artifact_uri", sa.Text(), nullable=True),
        sa.Column("generated_artifact_uri", sa.Text(), nullable=True),
        sa.Column("comparison_artifact_uri", sa.Text(), nullable=True),
        sa.Column("monitor_artifact_uri", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "total_draft_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "usable_draft_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "needs_prompt_tuning_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "dropped_draft_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(STATUS_CHECK, name="ck_data_generation_run_status_allowed"),
        sa.PrimaryKeyConstraint("id", name="pk_data_generation_run"),
    )
    op.create_index(
        "idx_generation_run_source_created",
        "data_generation_run",
        ["source_name", "created_at"],
        unique=False,
    )

    op.create_table(
        "data_generation_sample",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_run_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Text(), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=True),
        sa.Column("variant_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("parent_source", sa.Text(), nullable=True),
        sa.Column("target_label", sa.Text(), nullable=False),
        sa.Column("primary_theme", sa.Text(), nullable=True),
        sa.Column("review_state", sa.Text(), nullable=False),
        sa.Column("review_notes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("text_sha256", sa.Text(), nullable=True),
        sa.Column("nearest_reference_raw_record_id", sa.Uuid(), nullable=True),
        sa.Column("nearest_similarity", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            TARGET_LABEL_CHECK, name="ck_data_generation_sample_target_label_allowed"
        ),
        sa.CheckConstraint(
            REVIEW_STATE_CHECK, name="ck_data_generation_sample_review_state_allowed"
        ),
        sa.ForeignKeyConstraint(
            ["generation_run_id"],
            ["data_generation_run.id"],
            name="fk_data_generation_sample_generation_run_id_data_generation_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_generation_sample"),
        sa.UniqueConstraint(
            "generation_run_id",
            "draft_id",
            "variant_index",
            name="uq_generation_sample_run_draft_variant",
        ),
    )
    op.create_index(
        "idx_generation_sample_run_review",
        "data_generation_sample",
        ["generation_run_id", "review_state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_generation_sample_run_review", table_name="data_generation_sample"
    )
    op.drop_table("data_generation_sample")
    op.drop_index("idx_generation_run_source_created", table_name="data_generation_run")
    op.drop_table("data_generation_run")
