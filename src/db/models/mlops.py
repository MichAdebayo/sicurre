"""Operational model lineage and controlled-promotion records."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from db.models.lineage import utc_now

if TYPE_CHECKING:
    from db.models.lineage import DataDataset

JSON_VARIANT = sa.JSON().with_variant(JSONB(), "postgresql")


def enum_values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    """Return persisted values for a string enum."""
    return tuple(item.value for item in enum_cls)


class EvaluationSetStatus(StrEnum):
    """Human-review lifecycle for an immutable evaluation asset."""

    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ModelStage(StrEnum):
    """Operational stage of a registered model artifact."""

    CANDIDATE = "candidate"
    PRODUCTION = "production"
    RETIRED = "retired"
    REJECTED = "rejected"


class EvaluationOutcome(StrEnum):
    """Simple golden-set gate result."""

    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class DeploymentStatus(StrEnum):
    """Outcome of a manually approved production deployment."""

    ACTIVE = "active"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    RETIRED = "retired"


class DataEvaluationSet(Base):
    """Immutable reviewed asset kept outside model-training datasets."""

    __tablename__ = "data_evaluation_set"
    __table_args__ = (
        sa.CheckConstraint(
            f"status IN {enum_values(EvaluationSetStatus)}",
            name="evaluation_set_status_allowed",
        ),
        sa.UniqueConstraint("version_tag", name="uq_evaluation_set_version"),
        sa.UniqueConstraint("content_checksum", name="uq_evaluation_set_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    version_tag: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    schema_version: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    provenance: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text(), nullable=False, default=EvaluationSetStatus.DRAFT.value
    )
    object_uri: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    content_checksum: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    item_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    label_counts: Mapped[dict[str, int]] = mapped_column(JSON_VARIANT, nullable=False, default=dict)
    language_counts: Mapped[dict[str, int]] = mapped_column(
        JSON_VARIANT, nullable=False, default=dict
    )
    reviewed_by: Mapped[str | None] = mapped_column(sa.Text())
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    evaluations: Mapped[list[MlModelEvaluation]] = relationship(back_populates="evaluation_set")


class MlModelVersion(Base):
    """Cross-system identity of one candidate or production model artifact."""

    __tablename__ = "ml_model_version"
    __table_args__ = (
        sa.CheckConstraint(f"stage IN {enum_values(ModelStage)}", name="model_stage_allowed"),
        sa.UniqueConstraint("mlflow_run_id", name="uq_model_mlflow_run"),
        sa.UniqueConstraint("model_name", "mlflow_model_version", name="uq_model_registry_version"),
        sa.Index("idx_model_stage_created", "stage", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    semantic_version: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    service_source_revision: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    stage: Mapped[str] = mapped_column(
        sa.Text(), nullable=False, default=ModelStage.CANDIDATE.value
    )
    mlflow_run_id: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    mlflow_model_version: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    huggingface_repository: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    huggingface_revision: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    training_github_run_id: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    training_dataset_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_dataset.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), onupdate=utc_now
    )

    training_dataset: Mapped[DataDataset] = relationship("DataDataset")
    evaluations: Mapped[list[MlModelEvaluation]] = relationship(
        foreign_keys="MlModelEvaluation.candidate_model_id",
        back_populates="candidate_model",
    )
    deployments: Mapped[list[MlModelDeployment]] = relationship(
        foreign_keys="MlModelDeployment.model_version_id",
        back_populates="model_version",
    )


class MlModelEvaluation(Base):
    """Auditable decision snapshot pointing to full evidence in MLflow."""

    __tablename__ = "ml_model_evaluation"
    __table_args__ = (
        sa.CheckConstraint(
            f"outcome IN {enum_values(EvaluationOutcome)}",
            name="evaluation_outcome_allowed",
        ),
        sa.UniqueConstraint("mlflow_evaluation_run_id", name="uq_evaluation_mlflow_run"),
        sa.UniqueConstraint(
            "candidate_model_id", "evaluation_set_id", name="uq_candidate_evaluation_set"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    candidate_model_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("ml_model_version.id", ondelete="CASCADE"), nullable=False
    )
    incumbent_model_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("ml_model_version.id", ondelete="RESTRICT")
    )
    evaluation_set_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("data_evaluation_set.id", ondelete="RESTRICT"), nullable=False
    )
    mlflow_evaluation_run_id: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    outcome: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    metric_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_VARIANT, nullable=False, default=dict
    )
    policy_name: Mapped[str] = mapped_column(
        sa.Text(), nullable=False, default="provisional_synthetic_non_regression_v1"
    )
    evaluated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    candidate_model: Mapped[MlModelVersion] = relationship(
        foreign_keys=[candidate_model_id], back_populates="evaluations"
    )
    incumbent_model: Mapped[MlModelVersion | None] = relationship(foreign_keys=[incumbent_model_id])
    evaluation_set: Mapped[DataEvaluationSet] = relationship(back_populates="evaluations")
    deployments: Mapped[list[MlModelDeployment]] = relationship(back_populates="evaluation")


class MlModelDeployment(Base):
    """Result of one manually approved production promotion workflow."""

    __tablename__ = "ml_model_deployment"
    __table_args__ = (
        sa.CheckConstraint(
            f"status IN {enum_values(DeploymentStatus)}",
            name="deployment_status_allowed",
        ),
        sa.UniqueConstraint("github_run_id", name="uq_deployment_github_run"),
        sa.Index("idx_deployment_environment_created", "environment", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), primary_key=True, default=uuid.uuid4)
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("ml_model_version.id", ondelete="RESTRICT"), nullable=False
    )
    previous_model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("ml_model_version.id", ondelete="RESTRICT")
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("ml_model_evaluation.id", ondelete="RESTRICT"), nullable=False
    )
    environment: Mapped[str] = mapped_column(sa.Text(), nullable=False, default="production")
    status: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    github_run_id: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    approved_by: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    deployed_revision: Mapped[str | None] = mapped_column(sa.Text())
    failure_reason: Mapped[str | None] = mapped_column(sa.Text())
    deployed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now
    )

    model_version: Mapped[MlModelVersion] = relationship(
        foreign_keys=[model_version_id], back_populates="deployments"
    )
    previous_model_version: Mapped[MlModelVersion | None] = relationship(
        foreign_keys=[previous_model_version_id]
    )
    evaluation: Mapped[MlModelEvaluation] = relationship(back_populates="deployments")
