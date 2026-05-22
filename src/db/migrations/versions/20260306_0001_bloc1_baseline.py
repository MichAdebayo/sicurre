"""Create Bloc 1 data platform baseline.

Revision ID: 20260306_0001
Revises:
Create Date: 2026-03-06 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260306_0001"
down_revision = None
branch_labels = None
depends_on = None


SOURCE_TYPE_CHECK = (
    "source_type IN ('api', 'file', 'scraping', 'sql', 'bigdata', 'manual')"
)
STATUS_CHECK = "status IN ('pending', 'running', 'completed', 'failed', 'partial')"
OBJECT_TYPE_CHECK = "object_type IN ('file', 'api_payload', 'html_page', 'pdf_document', 'sql_export', 'bigdata_extract')"
LABEL_CHECK = "current_label IN ('phishing', 'spam', 'legitimate', 'unknown')"
ANNOTATION_LABEL_CHECK = "label IN ('phishing', 'spam', 'legitimate', 'unknown')"
REDACTION_CHECK = "redaction_status IN ('not_required', 'redacted', 'review_needed')"
DATASET_STATUS_CHECK = "status IN ('draft', 'frozen', 'archived')"
SPLIT_CHECK = "split_name IN ('train', 'val', 'test', 'holdout')"
CONFIDENCE_CHECK = "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)"


def upgrade() -> None:
    op.create_table(
        "data_source_system",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_name", sa.Text(), nullable=True),
        sa.Column("legal_basis", sa.Text(), nullable=True),
        sa.Column(
            "contains_personal_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            SOURCE_TYPE_CHECK, name="ck_data_source_system_source_type_allowed"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_source_system"),
        sa.UniqueConstraint("name", name="uq_data_source_system_name"),
    )

    op.create_table(
        "data_ingestion_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_system_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("trigger_mode", sa.Text(), nullable=False),
        sa.Column("raw_object_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("log_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(STATUS_CHECK, name="ck_data_ingestion_run_status_allowed"),
        sa.ForeignKeyConstraint(
            ["source_system_id"],
            ["data_source_system.id"],
            name="fk_data_ingestion_run_source_system_id_data_source_system",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_ingestion_run"),
    )
    op.create_index(
        "idx_ingestion_source_started",
        "data_ingestion_run",
        ["source_system_id", "started_at"],
        unique=False,
    )

    op.create_table(
        "data_raw_object",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("object_type", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("source_format", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            OBJECT_TYPE_CHECK, name="ck_data_raw_object_object_type_allowed"
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["data_ingestion_run.id"],
            name="fk_data_raw_object_ingestion_run_id_data_ingestion_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_raw_object"),
        sa.UniqueConstraint("content_hash", "external_ref", name="uq_raw_object_hash"),
    )
    op.create_index(
        "idx_raw_object_ingestion",
        "data_raw_object",
        ["ingestion_run_id"],
        unique=False,
    )

    op.create_table(
        "data_raw_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("raw_object_id", sa.Uuid(), nullable=False),
        sa.Column("source_system_id", sa.Uuid(), nullable=True),
        sa.Column("record_key", sa.Text(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("detected_language", sa.Text(), nullable=True),
        sa.Column("is_usable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["raw_object_id"],
            ["data_raw_object.id"],
            name="fk_data_raw_record_raw_object_id_data_raw_object",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_system_id"],
            ["data_source_system.id"],
            name="fk_data_raw_record_source_system_id_data_source_system",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_raw_record"),
        sa.UniqueConstraint("raw_object_id", "record_key", name="uq_raw_record_key"),
    )

    op.create_table(
        "data_processing_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_version", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("normalized_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_uri", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(STATUS_CHECK, name="ck_data_processing_run_status_allowed"),
        sa.PrimaryKeyConstraint("id", name="pk_data_processing_run"),
    )

    op.create_table(
        "data_normalized_message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("raw_record_id", sa.Uuid(), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("current_label", sa.Text(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column(
            "contains_pii", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "redaction_status", sa.Text(), nullable=False, server_default="not_required"
        ),
        sa.Column("text_length", sa.Integer(), nullable=False),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            LABEL_CHECK, name="ck_data_normalized_message_current_label_allowed"
        ),
        sa.CheckConstraint(
            REDACTION_CHECK, name="ck_data_normalized_message_redaction_status_allowed"
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id"],
            ["data_processing_run.id"],
            name="fk_data_norm_msg_processing_run_id_proc_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_record_id"],
            ["data_raw_record.id"],
            name="fk_data_normalized_message_raw_record_id_data_raw_record",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_normalized_message"),
        sa.UniqueConstraint(
            "text_sha256", name="uq_data_normalized_message_text_sha256"
        ),
    )
    op.create_index(
        "idx_message_label_lang",
        "data_normalized_message",
        ["current_label", "language"],
        unique=False,
    )
    op.create_index(
        "idx_message_processing_run",
        "data_normalized_message",
        ["processing_run_id"],
        unique=False,
    )

    op.create_table(
        "data_annotation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("normalized_message_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("label_source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "is_validated", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("annotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            ANNOTATION_LABEL_CHECK, name="ck_data_annotation_label_allowed"
        ),
        sa.CheckConstraint(
            CONFIDENCE_CHECK, name="ck_data_annotation_confidence_range"
        ),
        sa.ForeignKeyConstraint(
            ["normalized_message_id"],
            ["data_normalized_message.id"],
            name="fk_data_annotation_norm_msg_id_norm_msg",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_annotation"),
    )
    op.create_index(
        "idx_annotation_message_date",
        "data_annotation",
        ["normalized_message_id", "annotated_at"],
        unique=False,
    )

    op.create_table(
        "data_dataset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version_tag", sa.Text(), nullable=False),
        sa.Column("target_usage", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(DATASET_STATUS_CHECK, name="ck_data_dataset_status_allowed"),
        sa.PrimaryKeyConstraint("id", name="pk_data_dataset"),
        sa.UniqueConstraint("version_tag", name="uq_data_dataset_version_tag"),
    )

    op.create_table(
        "data_dataset_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_message_id", sa.Uuid(), nullable=False),
        sa.Column("split_name", sa.Text(), nullable=False),
        sa.Column("sample_weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("row_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(SPLIT_CHECK, name="ck_data_dataset_item_split_name_allowed"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["data_dataset.id"],
            name="fk_data_dataset_item_dataset_id_data_dataset",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["normalized_message_id"],
            ["data_normalized_message.id"],
            name="fk_data_dataset_item_norm_msg_id_norm_msg",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_dataset_item"),
        sa.UniqueConstraint(
            "dataset_id", "normalized_message_id", name="uq_dataset_message"
        ),
    )
    op.create_index(
        "idx_dataset_split",
        "data_dataset_item",
        ["dataset_id", "split_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_dataset_split", table_name="data_dataset_item")
    op.drop_table("data_dataset_item")
    op.drop_table("data_dataset")
    op.drop_index("idx_annotation_message_date", table_name="data_annotation")
    op.drop_table("data_annotation")
    op.drop_index("idx_message_processing_run", table_name="data_normalized_message")
    op.drop_index("idx_message_label_lang", table_name="data_normalized_message")
    op.drop_table("data_normalized_message")
    op.drop_table("data_processing_run")
    op.drop_table("data_raw_record")
    op.drop_index("idx_raw_object_ingestion", table_name="data_raw_object")
    op.drop_table("data_raw_object")
    op.drop_index("idx_ingestion_source_started", table_name="data_ingestion_run")
    op.drop_table("data_ingestion_run")
    op.drop_table("data_source_system")
