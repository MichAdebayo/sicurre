from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


JSON_VARIANT = sa.JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    return tuple(item.value for item in enum_cls)


class SourceType(StrEnum):
    API = "api"
    FILE = "file"
    SCRAPING = "scraping"
    SQL = "sql"
    BIGDATA = "bigdata"
    MANUAL = "manual"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ObjectType(StrEnum):
    FILE = "file"
    API_PAYLOAD = "api_payload"
    HTML_PAGE = "html_page"
    PDF_DOCUMENT = "pdf_document"
    SQL_EXPORT = "sql_export"
    BIGDATA_EXTRACT = "bigdata_extract"


class NormalizedLabel(StrEnum):
    PHISHING = "phishing"
    SPAM = "spam"
    LEGITIMATE = "legitimate"
    UNKNOWN = "unknown"


class RedactionStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    REDACTED = "redacted"
    REVIEW_NEEDED = "review_needed"


class AnnotationLabel(StrEnum):
    PHISHING = "phishing"
    SPAM = "spam"
    LEGITIMATE = "legitimate"
    UNKNOWN = "unknown"


class DatasetStatus(StrEnum):
    DRAFT = "draft"
    FROZEN = "frozen"
    ARCHIVED = "archived"


class SplitName(StrEnum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"
    HOLDOUT = "holdout"


class DataSourceSystem(Base):
    __tablename__ = "data_source_system"
    __table_args__ = (
        sa.CheckConstraint(
            f"source_type IN {enum_values(SourceType)}",
            name="source_type_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.Text(), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text())
    owner_name: Mapped[str | None] = mapped_column(sa.Text())
    legal_basis: Mapped[str | None] = mapped_column(sa.Text())
    contains_personal_data: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False
    )
    retention_days: Mapped[int | None] = mapped_column(sa.Integer())
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), onupdate=utc_now
    )

    ingestion_runs: Mapped[list[DataIngestionRun]] = relationship(
        back_populates="source_system"
    )


class DataIngestionRun(Base):
    __tablename__ = "data_ingestion_run"
    __table_args__ = (
        sa.CheckConstraint(
            f"status IN {enum_values(IngestionStatus)}",
            name="status_allowed",
        ),
        sa.Index("idx_ingestion_source_started", "source_system_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    source_system_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_source_system.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    trigger_mode: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    raw_object_count: Mapped[int] = mapped_column(
        sa.Integer(), nullable=False, default=0
    )
    raw_record_count: Mapped[int] = mapped_column(
        sa.Integer(), nullable=False, default=0
    )
    log_message: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    source_system: Mapped[DataSourceSystem] = relationship(
        back_populates="ingestion_runs"
    )
    raw_objects: Mapped[list[DataRawObject]] = relationship(
        back_populates="ingestion_run"
    )


class DataRawObject(Base):
    __tablename__ = "data_raw_object"
    __table_args__ = (
        sa.CheckConstraint(
            f"object_type IN {enum_values(ObjectType)}",
            name="object_type_allowed",
        ),
        sa.UniqueConstraint("content_hash", "external_ref", name="uq_raw_object_hash"),
        sa.Index("idx_raw_object_ingestion", "ingestion_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_ingestion_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_ref: Mapped[str | None] = mapped_column(sa.Text())
    object_type: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(sa.Text())
    source_format: Mapped[str | None] = mapped_column(sa.Text())
    content_hash: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger())
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON_VARIANT, nullable=False, default=dict
    )
    collected_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    retention_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    ingestion_run: Mapped[DataIngestionRun] = relationship(back_populates="raw_objects")
    raw_records: Mapped[list[DataRawRecord]] = relationship(back_populates="raw_object")


class DataRawRecord(Base):
    __tablename__ = "data_raw_record"
    __table_args__ = (
        sa.UniqueConstraint("raw_object_id", "record_key", name="uq_raw_record_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    raw_object_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_raw_object.id", ondelete="CASCADE"),
        nullable=False,
    )
    record_key: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    raw_content: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    detected_language: Mapped[str | None] = mapped_column(sa.Text())
    is_usable: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=True)
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text())
    extracted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    raw_object: Mapped[DataRawObject] = relationship(back_populates="raw_records")
    normalized_messages: Mapped[list[DataNormalizedMessage]] = relationship(
        back_populates="raw_record"
    )


class DataProcessingRun(Base):
    __tablename__ = "data_processing_run"
    __table_args__ = (
        sa.CheckConstraint(
            f"status IN {enum_values(IngestionStatus)}",
            name="status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    pipeline_version: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    normalized_count: Mapped[int] = mapped_column(
        sa.Integer(), nullable=False, default=0
    )
    rejected_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0)
    report_uri: Mapped[str | None] = mapped_column(sa.Text())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    normalized_messages: Mapped[list[DataNormalizedMessage]] = relationship(
        back_populates="processing_run"
    )


class DataNormalizedMessage(Base):
    __tablename__ = "data_normalized_message"
    __table_args__ = (
        sa.CheckConstraint(
            f"current_label IN {enum_values(NormalizedLabel)}",
            name="current_label_allowed",
        ),
        sa.CheckConstraint(
            f"redaction_status IN {enum_values(RedactionStatus)}",
            name="redaction_status_allowed",
        ),
        sa.Index("idx_message_label_lang", "current_label", "language"),
        sa.Index("idx_message_processing_run", "processing_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    raw_record_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_raw_record.id", ondelete="RESTRICT"),
        nullable=False,
    )
    processing_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_processing_run.id", ondelete="RESTRICT"),
        nullable=False,
    )
    normalized_text: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    text_sha256: Mapped[str] = mapped_column(sa.Text(), nullable=False, unique=True)
    language: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    current_label: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    quality_score: Mapped[float | None] = mapped_column(sa.Float())
    contains_pii: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False
    )
    redaction_status: Mapped[str] = mapped_column(
        sa.Text(),
        nullable=False,
        default=RedactionStatus.NOT_REQUIRED.value,
    )
    text_length: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    normalized_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), onupdate=utc_now
    )

    raw_record: Mapped[DataRawRecord] = relationship(
        back_populates="normalized_messages"
    )
    processing_run: Mapped[DataProcessingRun] = relationship(
        back_populates="normalized_messages"
    )
    annotations: Mapped[list[DataAnnotation]] = relationship(
        back_populates="normalized_message"
    )
    dataset_items: Mapped[list[DataDatasetItem]] = relationship(
        back_populates="normalized_message"
    )


class DataAnnotation(Base):
    __tablename__ = "data_annotation"
    __table_args__ = (
        sa.CheckConstraint(
            f"label IN {enum_values(AnnotationLabel)}",
            name="label_allowed",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        sa.Index(
            "idx_annotation_message_date", "normalized_message_id", "annotated_at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    normalized_message_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_normalized_message.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    label_source: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    confidence: Mapped[float | None] = mapped_column(sa.Float())
    comment: Mapped[str | None] = mapped_column(sa.Text())
    is_validated: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False
    )
    annotated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    normalized_message: Mapped[DataNormalizedMessage] = relationship(
        back_populates="annotations"
    )


class DataDataset(Base):
    __tablename__ = "data_dataset"
    __table_args__ = (
        sa.CheckConstraint(
            f"status IN {enum_values(DatasetStatus)}",
            name="status_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    version_tag: Mapped[str] = mapped_column(sa.Text(), nullable=False, unique=True)
    target_usage: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    status: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    item_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), onupdate=utc_now
    )

    items: Mapped[list[DataDatasetItem]] = relationship(back_populates="dataset")


class DataDatasetItem(Base):
    __tablename__ = "data_dataset_item"
    __table_args__ = (
        sa.CheckConstraint(
            f"split_name IN {enum_values(SplitName)}",
            name="split_name_allowed",
        ),
        sa.UniqueConstraint(
            "dataset_id", "normalized_message_id", name="uq_dataset_message"
        ),
        sa.Index("idx_dataset_split", "dataset_id", "split_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_dataset.id", ondelete="CASCADE"),
        nullable=False,
    )
    normalized_message_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_normalized_message.id", ondelete="RESTRICT"),
        nullable=False,
    )
    split_name: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    sample_weight: Mapped[float] = mapped_column(
        sa.Float(), nullable=False, default=1.0
    )
    row_order: Mapped[int | None] = mapped_column(sa.Integer())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    dataset: Mapped[DataDataset] = relationship(back_populates="items")
    normalized_message: Mapped[DataNormalizedMessage] = relationship(
        back_populates="dataset_items"
    )
