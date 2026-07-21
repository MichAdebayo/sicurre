"""Persistence rules for cross-repository model provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_platform.api.schemas.mlops import (
    EvaluationSetRegistration,
    ModelCandidateRegistration,
    ModelDeploymentRegistration,
    ModelEvaluationRegistration,
)
from db.models import (
    DataDataset,
    DataEvaluationSet,
    DeploymentStatus,
    EvaluationOutcome,
    EvaluationSetStatus,
    MlModelDeployment,
    MlModelEvaluation,
    MlModelVersion,
    ModelStage,
)


class ModelProvenanceError(RuntimeError):
    """Typed model-lineage persistence failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PersistedRecord:
    """Identity and replay state returned by persistence operations."""

    id: str
    status: str
    idempotent: bool


def _same(record: Any, expected: dict[str, Any]) -> bool:
    """Compare persisted values required to make an external replay safe."""
    return all(_equal_persisted(getattr(record, key), value) for key, value in expected.items())


def _equal_persisted(actual: Any, expected: Any) -> bool:
    """Normalize timezone handling across PostgreSQL and local SQLite."""
    if isinstance(actual, datetime) and isinstance(expected, datetime):
        actual_utc = actual.replace(tzinfo=actual.tzinfo or UTC).astimezone(UTC)
        expected_utc = expected.replace(tzinfo=expected.tzinfo or UTC).astimezone(UTC)
        return actual_utc == expected_utc
    return bool(actual == expected)


async def register_evaluation_set(
    session: AsyncSession, payload: EvaluationSetRegistration
) -> PersistedRecord:
    """Register or approve one immutable golden-set manifest."""
    existing = (
        await session.execute(
            select(DataEvaluationSet).where(DataEvaluationSet.version_tag == payload.version_tag)
        )
    ).scalar_one_or_none()
    immutable = {
        "name": payload.name,
        "schema_version": payload.schema_version,
        "provenance": payload.provenance,
        "content_checksum": payload.content_checksum.lower(),
        "item_count": payload.item_count,
        "label_counts": payload.label_counts,
        "language_counts": payload.language_counts,
    }
    if existing:
        if not _same(existing, immutable):
            raise ModelProvenanceError(
                "evaluation_set_conflict",
                "The evaluation-set version already exists with different content.",
            )
        existing.object_uri = payload.object_uri
        if payload.status == EvaluationSetStatus.APPROVED.value:
            existing.status = payload.status
            existing.reviewed_by = payload.reviewed_by
            existing.reviewed_at = payload.reviewed_at
            await session.commit()
        return PersistedRecord(str(existing.id), existing.status, True)

    record = DataEvaluationSet(
        **immutable,
        version_tag=payload.version_tag,
        object_uri=payload.object_uri,
        status=payload.status,
        reviewed_by=payload.reviewed_by,
        reviewed_at=payload.reviewed_at,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return PersistedRecord(str(record.id), record.status, False)


async def register_candidate(
    session: AsyncSession, payload: ModelCandidateRegistration
) -> PersistedRecord:
    """Register a trained model as a candidate without promoting it."""
    dataset = (
        await session.execute(
            select(DataDataset).where(
                DataDataset.version_tag == payload.training_dataset_version_tag
            )
        )
    ).scalar_one_or_none()
    if not dataset:
        raise ModelProvenanceError(
            "training_dataset_not_found", "The frozen training dataset is unknown."
        )
    existing = (
        await session.execute(
            select(MlModelVersion).where(MlModelVersion.mlflow_run_id == payload.mlflow_run_id)
        )
    ).scalar_one_or_none()
    expected = {
        "model_name": payload.model_name,
        "semantic_version": payload.semantic_version,
        "service_source_revision": payload.service_source_revision.lower(),
        "mlflow_model_version": payload.mlflow_model_version,
        "huggingface_repository": payload.huggingface_repository,
        "huggingface_revision": payload.huggingface_revision,
        "training_github_run_id": payload.training_github_run_id,
        "training_dataset_id": dataset.id,
    }
    if existing:
        if not _same(existing, expected):
            raise ModelProvenanceError(
                "candidate_conflict",
                "The MLflow run is already linked to a different candidate.",
            )
        return PersistedRecord(str(existing.id), existing.stage, True)

    record = MlModelVersion(
        **expected,
        mlflow_run_id=payload.mlflow_run_id,
        stage=ModelStage.CANDIDATE.value,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return PersistedRecord(str(record.id), record.stage, False)


async def register_evaluation(
    session: AsyncSession, payload: ModelEvaluationRegistration
) -> PersistedRecord:
    """Record the bounded decision snapshot while leaving full metrics in MLflow."""
    candidate = (
        await session.execute(
            select(MlModelVersion).where(
                MlModelVersion.mlflow_run_id == payload.candidate_mlflow_run_id
            )
        )
    ).scalar_one_or_none()
    if not candidate:
        raise ModelProvenanceError("candidate_not_found", "The candidate is unknown.")
    evaluation_set = (
        await session.execute(
            select(DataEvaluationSet).where(
                DataEvaluationSet.version_tag == payload.evaluation_set_version_tag
            )
        )
    ).scalar_one_or_none()
    if not evaluation_set or evaluation_set.status != EvaluationSetStatus.APPROVED.value:
        raise ModelProvenanceError(
            "approved_evaluation_set_required",
            "The evaluation set must exist and be human-approved.",
        )
    if evaluation_set.content_checksum != payload.evaluation_set_checksum.lower():
        raise ModelProvenanceError(
            "evaluation_set_checksum_mismatch",
            "The evaluation-set checksum does not match the approved manifest.",
        )
    incumbent = None
    if payload.incumbent_huggingface_revision:
        incumbent = (
            await session.execute(
                select(MlModelVersion).where(
                    MlModelVersion.huggingface_revision == payload.incumbent_huggingface_revision
                )
            )
        ).scalar_one_or_none()
    existing = (
        await session.execute(
            select(MlModelEvaluation).where(
                MlModelEvaluation.mlflow_evaluation_run_id == payload.mlflow_evaluation_run_id
            )
        )
    ).scalar_one_or_none()
    expected = {
        "candidate_model_id": candidate.id,
        "incumbent_model_id": incumbent.id if incumbent else None,
        "evaluation_set_id": evaluation_set.id,
        "outcome": payload.outcome,
        "metric_snapshot": payload.metrics.model_dump(),
        "evaluated_at": payload.evaluated_at,
    }
    if existing:
        if not _same(existing, expected):
            raise ModelProvenanceError(
                "evaluation_conflict",
                "The MLflow evaluation run already has a different decision.",
            )
        return PersistedRecord(str(existing.id), existing.outcome, True)

    record = MlModelEvaluation(
        **expected,
        mlflow_evaluation_run_id=payload.mlflow_evaluation_run_id,
    )
    session.add(record)
    if payload.outcome == EvaluationOutcome.FAILED.value:
        candidate.stage = ModelStage.REJECTED.value
    await session.commit()
    await session.refresh(record)
    return PersistedRecord(str(record.id), record.outcome, False)


async def register_deployment(
    session: AsyncSession, payload: ModelDeploymentRegistration
) -> PersistedRecord:
    """Record the outcome of the manually approved production workflow."""
    candidate = (
        await session.execute(
            select(MlModelVersion).where(
                MlModelVersion.mlflow_run_id == payload.candidate_mlflow_run_id
            )
        )
    ).scalar_one_or_none()
    evaluation = (
        await session.execute(
            select(MlModelEvaluation).where(
                MlModelEvaluation.mlflow_evaluation_run_id == payload.mlflow_evaluation_run_id
            )
        )
    ).scalar_one_or_none()
    if not candidate or not evaluation or evaluation.candidate_model_id != candidate.id:
        raise ModelProvenanceError(
            "promotion_lineage_not_found",
            "Candidate and evaluation lineage must exist before deployment.",
        )
    if payload.status == DeploymentStatus.ACTIVE.value:
        if evaluation.outcome != EvaluationOutcome.PASSED.value:
            raise ModelProvenanceError(
                "passing_evaluation_required",
                "Only a candidate with a passing evaluation can become active.",
            )
        if candidate.huggingface_revision != payload.deployed_revision:
            raise ModelProvenanceError(
                "deployed_revision_mismatch",
                "The deployed revision does not match the candidate artifact.",
            )
    existing = (
        await session.execute(
            select(MlModelDeployment).where(
                MlModelDeployment.github_run_id == payload.github_run_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        expected = {
            "model_version_id": candidate.id,
            "evaluation_id": evaluation.id,
            "status": payload.status,
            "deployed_revision": payload.deployed_revision,
        }
        if not _same(existing, expected):
            raise ModelProvenanceError(
                "deployment_conflict",
                "The promotion workflow run already has a different result.",
            )
        return PersistedRecord(str(existing.id), existing.status, True)

    previous = (
        (
            await session.execute(
                select(MlModelVersion).where(
                    MlModelVersion.stage == ModelStage.PRODUCTION.value,
                    MlModelVersion.id != candidate.id,
                )
            )
        )
        .scalars()
        .first()
    )
    record = MlModelDeployment(
        model_version_id=candidate.id,
        previous_model_version_id=previous.id if previous else None,
        evaluation_id=evaluation.id,
        environment="production",
        status=payload.status,
        github_run_id=payload.github_run_id,
        approved_by=payload.approved_by,
        approved_at=payload.approved_at,
        deployed_revision=payload.deployed_revision,
        failure_reason=payload.failure_reason,
        deployed_at=payload.deployed_at,
    )
    session.add(record)
    if payload.status == DeploymentStatus.ACTIVE.value:
        now = payload.deployed_at or datetime.now(UTC)
        candidate.stage = ModelStage.PRODUCTION.value
        candidate.huggingface_revision = payload.deployed_revision
        if previous:
            previous.stage = ModelStage.RETIRED.value
            previous_deployments = (
                await session.execute(
                    select(MlModelDeployment).where(
                        MlModelDeployment.model_version_id == previous.id,
                        MlModelDeployment.status == DeploymentStatus.ACTIVE.value,
                    )
                )
            ).scalars()
            for deployment in previous_deployments:
                deployment.status = DeploymentStatus.RETIRED.value
                deployment.retired_at = now
    await session.commit()
    await session.refresh(record)
    return PersistedRecord(str(record.id), record.status, False)
