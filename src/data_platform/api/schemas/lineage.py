from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from db.models import (
    AnnotationLabel,
    AnnotationLabelSource,
    DatasetStatus,
    IngestionStatus,
    NormalizedLabel,
    RedactionStatus,
    SourceType,
    SplitName,
)


class RawRecordRead(BaseModel):
    id: UUID
    raw_object_id: UUID
    record_key: str
    raw_content: str
    detected_language: str | None = None
    is_usable: bool
    rejection_reason: str | None = None
    extracted_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RawRecordListResponse(BaseModel):
    items: list[RawRecordRead]
    total: int


class NormalizedMessageCreate(BaseModel):
    raw_record_id: UUID
    processing_run_id: UUID
    normalized_text: str = Field(min_length=1)
    language: str
    current_label: NormalizedLabel
    quality_score: float | None = None
    contains_pii: bool = False
    redaction_status: RedactionStatus = RedactionStatus.NOT_REQUIRED


class NormalizedMessageUpdate(BaseModel):
    current_label: NormalizedLabel | None = None
    quality_score: float | None = None
    redaction_status: RedactionStatus | None = None


class NormalizedMessageRead(NormalizedMessageCreate):
    id: UUID
    text_sha256: str
    text_length: int
    normalized_at: datetime
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class NormalizedMessageListResponse(BaseModel):
    items: list[NormalizedMessageRead]
    total: int


class AnnotationCreate(BaseModel):
    normalized_message_id: UUID
    label: AnnotationLabel
    label_source: AnnotationLabelSource
    confidence: float | None = None
    comment: str | None = None
    is_validated: bool = False
    annotated_at: datetime


class AnnotationRead(AnnotationCreate):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1)
    version_tag: str = Field(min_length=1)
    target_usage: str = Field(min_length=1)
    status: DatasetStatus


class DatasetRead(DatasetCreate):
    id: UUID
    frozen_at: datetime | None = None
    item_count: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DatasetListResponse(BaseModel):
    items: list[DatasetRead]
    total: int


class DatasetPublishResponse(BaseModel):
    kaggle_url: str
    kaggle_version_id: int
    github_dispatch_sent: bool


class DatasetItemRead(BaseModel):
    id: UUID
    dataset_id: UUID
    normalized_message_id: UUID
    split_name: SplitName
    sample_weight: float
    row_order: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetItemListResponse(BaseModel):
    items: list[DatasetItemRead]
    total: int


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1)
    source_type: SourceType
    description: str | None = None
    owner_name: str | None = None
    legal_basis: str | None = None
    contains_personal_data: bool = False
    retention_days: int | None = Field(default=None, ge=1)


class DataSourceRead(DataSourceCreate):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DataSourceListResponse(BaseModel):
    items: list[DataSourceRead]
    total: int


class IngestionRunCreate(BaseModel):
    source_system_id: UUID
    started_at: datetime
    status: IngestionStatus
    trigger_mode: str = Field(min_length=1)
    finished_at: datetime | None = None
    raw_object_count: int = Field(default=0, ge=0)
    raw_record_count: int = Field(default=0, ge=0)
    log_message: str | None = None


class IngestionRunRead(IngestionRunCreate):
    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionRunListResponse(BaseModel):
    items: list[IngestionRunRead]
    total: int
