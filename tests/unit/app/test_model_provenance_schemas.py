"""Validation tests for the bounded model-promotion callback contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from data_platform.api.schemas.mlops import (
    EvaluationSetRegistration,
    ModelCandidateRegistration,
    ModelDeploymentRegistration,
    ModelEvaluationRegistration,
    PromotionMetricSnapshot,
)


def test_candidate_requires_immutable_code_and_artifact_revisions() -> None:
    """A mutable or unidentified artifact cannot enter the promotion path."""
    base = {
        "model_name": "sicurre-phishing",
        "semantic_version": "2.0.0",
        "service_source_revision": "c" * 40,
        "mlflow_run_id": "candidate-run",
        "mlflow_model_version": "42",
        "huggingface_repository": "sicurre/model",
        "huggingface_revision": "a" * 40,
        "training_github_run_id": "29664567490",
        "training_dataset_version_tag": "base-20260718-144342",
    }
    assert ModelCandidateRegistration.model_validate(base).semantic_version == "2.0.0"
    with pytest.raises(ValidationError):
        ModelCandidateRegistration.model_validate({**base, "service_source_revision": "main"})
    with pytest.raises(ValidationError):
        ModelCandidateRegistration.model_validate({**base, "huggingface_revision": ""})


def test_promotion_snapshot_applies_three_simple_gates() -> None:
    """F1, phishing recall, and legitimate false positives determine passage."""
    passing = PromotionMetricSnapshot(
        candidate_weighted_f1=0.92,
        production_weighted_f1=0.92,
        candidate_phishing_recall=0.98,
        production_phishing_recall=0.97,
        candidate_legitimate_false_positives=1,
        production_legitimate_false_positives=1,
    )
    failing = passing.model_copy(update={"candidate_phishing_recall": 0.96})
    assert passing.passes() is True
    assert failing.passes() is False


def test_approved_evaluation_set_requires_review_and_balanced_counts() -> None:
    """Synthetic generation is not accepted as ground truth without review."""
    base = {
        "name": "golden",
        "version_tag": "v1",
        "schema_version": "1",
        "provenance": "synthetic_provisional",
        "status": "approved",
        "object_uri": "r2://bucket/golden.jsonl",
        "content_checksum": "a" * 64,
        "item_count": 2,
        "label_counts": {"phishing": 1, "legitimate": 1},
        "language_counts": {"fr": 2},
    }
    with pytest.raises(ValidationError):
        EvaluationSetRegistration.model_validate(base)
    with pytest.raises(ValidationError):
        EvaluationSetRegistration.model_validate(
            {**base, "reviewed_by": "owner", "reviewed_at": "2026-07-19T10:00:00Z", "item_count": 3}
        )
    with pytest.raises(ValidationError):
        EvaluationSetRegistration.model_validate(
            {
                **base,
                "reviewed_by": "owner",
                "reviewed_at": "2026-07-19T10:00:00Z",
                "language_counts": {"fr": 1},
            }
        )
    with pytest.raises(ValidationError, match="only French"):
        EvaluationSetRegistration.model_validate(
            {
                **base,
                "reviewed_by": "owner",
                "reviewed_at": "2026-07-19T10:00:00Z",
                "language_counts": {"fr": 1, "en": 1},
            }
        )


def test_reported_evaluation_outcome_must_match_metrics() -> None:
    """A callback cannot label a regressing candidate as passed."""
    with pytest.raises(ValidationError):
        ModelEvaluationRegistration.model_validate(
            {
                "candidate_mlflow_run_id": "candidate",
                "evaluation_set_version_tag": "golden-v1",
                "evaluation_set_checksum": "a" * 64,
                "mlflow_evaluation_run_id": "evaluation",
                "outcome": "passed",
                "metrics": {
                    "candidate_weighted_f1": 0.8,
                    "production_weighted_f1": 0.9,
                    "candidate_phishing_recall": 0.9,
                    "production_phishing_recall": 0.9,
                    "candidate_legitimate_false_positives": 0,
                    "production_legitimate_false_positives": 0,
                },
                "evaluated_at": "2026-07-19T10:00:00Z",
            }
        )


@pytest.mark.parametrize("status", ["failed", "rolled_back"])
def test_non_active_deployment_requires_failure_reason(status: str) -> None:
    """Failure callbacks preserve an actionable bounded reason."""
    with pytest.raises(ValidationError):
        ModelDeploymentRegistration.model_validate(
            {
                "candidate_mlflow_run_id": "candidate",
                "mlflow_evaluation_run_id": "evaluation",
                "github_run_id": "workflow",
                "approved_by": "owner",
                "approved_at": "2026-07-19T10:00:00Z",
                "status": status,
            }
        )


def test_active_deployment_requires_revision_and_time() -> None:
    """A production identity cannot be recorded without immutable evidence."""
    with pytest.raises(ValidationError):
        ModelDeploymentRegistration.model_validate(
            {
                "candidate_mlflow_run_id": "candidate",
                "mlflow_evaluation_run_id": "evaluation",
                "github_run_id": "workflow",
                "approved_by": "owner",
                "approved_at": "2026-07-19T10:00:00Z",
                "status": "active",
            }
        )
