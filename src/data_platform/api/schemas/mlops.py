"""Typed contracts for ML lineage callbacks."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EvaluationSetRegistration(BaseModel):
    """Immutable golden-set manifest registered by the data-platform owner."""

    name: str = Field(min_length=1, max_length=200)
    version_tag: str = Field(min_length=1, max_length=120)
    schema_version: str = Field(min_length=1, max_length=50)
    provenance: Literal["synthetic_provisional"]
    status: Literal["draft", "approved"] = "draft"
    object_uri: str = Field(pattern=r"^r2://[^/]+/.+")
    content_checksum: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    item_count: int = Field(gt=0)
    label_counts: dict[str, int]
    language_counts: dict[str, int]
    reviewed_by: str | None = Field(default=None, max_length=320)
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_review(self) -> EvaluationSetRegistration:
        """Require reviewer evidence before an evaluation set is approved."""
        if self.status == "approved" and not (self.reviewed_by and self.reviewed_at):
            raise ValueError("Approved evaluation sets require reviewer and review time")
        if sum(self.label_counts.values()) != self.item_count:
            raise ValueError("Label counts must equal item_count")
        if sum(self.language_counts.values()) != self.item_count:
            raise ValueError("Language counts must equal item_count")
        if self.language_counts != {"fr": self.item_count}:
            raise ValueError("Sicurre evaluation sets must contain only French records")
        return self


class ModelCandidateRegistration(BaseModel):
    """Identity emitted after a successful candidate training run."""

    model_name: str = Field(min_length=1, max_length=200)
    semantic_version: str = Field(min_length=1, max_length=80)
    service_source_revision: str = Field(pattern=r"^[a-fA-F0-9]{40}$")
    mlflow_run_id: str = Field(min_length=1, max_length=200)
    mlflow_model_version: str = Field(min_length=1, max_length=100)
    huggingface_repository: str = Field(min_length=1, max_length=300)
    huggingface_revision: str = Field(min_length=7, max_length=200)
    training_github_run_id: str = Field(min_length=1, max_length=100)
    training_dataset_version_tag: str = Field(min_length=1, max_length=120)


#: Non-inferiority margin on phishing recall, mirroring
#: ``sicurre-ml/src/evaluation/promotion.py::PromotionThresholds``.
#:
#: DUPLICATED RULE - the two must move together. This class re-derives the gate
#: independently so a reported pass cannot contradict the metrics behind it,
#: which is deliberate defence in depth; the cost is that a margin changed in
#: one repository and not the other rejects every evaluation with HTTP 422 and
#: no obvious cause. That is exactly what happened on 2 September 2026, on the
#: first candidate ever to pass.
#:
#: The value is derived, not chosen: phishing recall is estimated on 42 golden
#: samples, where the incumbent's 0.8810 carries a Wilson 95% half-width of
#: 0.0990. A margin of 0.099 declines to reject on a difference the evaluation
#: set cannot distinguish from zero. Re-derive it when the golden set changes
#: size, in both repositories.
PHISHING_RECALL_REGRESSION_TOLERANCE = 0.099


class PromotionMetricSnapshot(BaseModel):
    """Minimal reproducible values used by the non-regression gate."""

    candidate_weighted_f1: float = Field(ge=0, le=1)
    production_weighted_f1: float = Field(ge=0, le=1)
    candidate_phishing_recall: float = Field(ge=0, le=1)
    production_phishing_recall: float = Field(ge=0, le=1)
    candidate_legitimate_false_positives: int = Field(ge=0)
    production_legitimate_false_positives: int = Field(ge=0)

    def passes(self) -> bool:
        """Apply the provisional three-part non-regression policy."""
        return (
            self.candidate_weighted_f1 >= self.production_weighted_f1
            and self.candidate_phishing_recall
            >= self.production_phishing_recall - PHISHING_RECALL_REGRESSION_TOLERANCE
            and self.candidate_legitimate_false_positives
            <= self.production_legitimate_false_positives
        )


class ModelEvaluationRegistration(BaseModel):
    """Golden-set decision produced by Sicurre-ML and linked to MLflow."""

    candidate_mlflow_run_id: str = Field(min_length=1, max_length=200)
    incumbent_huggingface_revision: str | None = Field(default=None, max_length=200)
    evaluation_set_version_tag: str = Field(min_length=1, max_length=120)
    evaluation_set_checksum: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    mlflow_evaluation_run_id: str = Field(min_length=1, max_length=200)
    outcome: Literal["passed", "failed", "inconclusive"]
    metrics: PromotionMetricSnapshot
    evaluated_at: datetime

    @model_validator(mode="after")
    def validate_outcome(self) -> ModelEvaluationRegistration:
        """Prevent a reported pass from contradicting the shared gate."""
        expected = "passed" if self.metrics.passes() else "failed"
        if self.outcome != "inconclusive" and self.outcome != expected:
            raise ValueError("Evaluation outcome contradicts the promotion metrics")
        return self


class ModelDeploymentRegistration(BaseModel):
    """Result returned by the manually approved production workflow."""

    candidate_mlflow_run_id: str = Field(min_length=1, max_length=200)
    mlflow_evaluation_run_id: str = Field(min_length=1, max_length=200)
    github_run_id: str = Field(min_length=1, max_length=100)
    approved_by: str = Field(min_length=1, max_length=320)
    approved_at: datetime
    status: Literal["active", "failed", "rolled_back"]
    deployed_revision: str | None = Field(default=None, max_length=200)
    failure_reason: str | None = Field(default=None, max_length=1000)
    deployed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_result(self) -> ModelDeploymentRegistration:
        """Require immutable revision evidence for a successful deployment."""
        if self.status == "active" and not (self.deployed_revision and self.deployed_at):
            raise ValueError("Active deployments require revision and deployment time")
        if self.status != "active" and not self.failure_reason:
            raise ValueError("Failed or rolled-back deployments require a reason")
        return self


class LineageRecordResponse(BaseModel):
    """Stable identity returned for an idempotently persisted record."""

    id: str
    status: str
    idempotent: bool
