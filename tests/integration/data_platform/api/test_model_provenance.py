"""Model provenance persistence and internal callback tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.config import Settings, get_settings
from core.database import Base, get_async_session
from data_platform.api.main import create_app
from db.models import (
    DataDataset,
    DeploymentStatus,
    MlModelDeployment,
    MlModelVersion,
    ModelStage,
)

AUTH_HEADERS = {"Authorization": "Bearer ml-callback-key"}
CHECKSUM = "a" * 64
NOW = "2026-07-19T10:00:00Z"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide an isolated schema containing both lineage and MLOps tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """Expose internal callbacks with a deterministic service credential."""
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session
    callback_settings = Settings(_env_file=None).model_copy(
        update={"internal_api_key": "ml-callback-key"}
    )
    app.dependency_overrides[get_settings] = lambda: callback_settings
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def frozen_dataset(
    session_factory: async_sessionmaker[AsyncSession],
) -> DataDataset:
    """Seed the immutable training dataset referenced by candidates."""
    async with session_factory() as session:
        dataset = DataDataset(
            name="sicurre-data",
            version_tag="base-20260718-144342",
            target_usage="training",
            status="frozen",
            frozen_at=datetime.now(UTC),
            item_count=32591,
            content_checksum="b" * 64,
            artifact_uri="r2://sicurre-datasets/base-20260718-144342/manifest.json",
            schema_version="1",
        )
        session.add(dataset)
        await session.commit()
        await session.refresh(dataset)
        return dataset


def evaluation_set_payload(status: str = "approved") -> dict[str, object]:
    """Build a reviewed synthetic golden-set manifest."""
    payload: dict[str, object] = {
        "name": "sicurre-provisional-golden-set",
        "version_tag": "golden-20260719-v1",
        "schema_version": "1",
        "provenance": "synthetic_provisional",
        "status": status,
        "object_uri": "r2://sicurre-golden-evaluation-dataset/golden.jsonl",
        "content_checksum": CHECKSUM,
        "item_count": 60,
        "label_counts": {"phishing": 25, "legitimate": 25, "spam": 10},
        "language_counts": {"fr": 60},
    }
    if status == "approved":
        payload.update({"reviewed_by": "owner@sicurre.com", "reviewed_at": NOW})
    return payload


def candidate_payload(run_id: str = "mlflow-candidate-1") -> dict[str, object]:
    """Build one candidate completion callback."""
    return {
        "model_name": "main.sicurre.phishing-detector",
        "semantic_version": "2.0.0",
        "service_source_revision": "c8676c85f54571adfb6669532755ba3023ac7d35",
        "mlflow_run_id": run_id,
        "mlflow_model_version": "42" if run_id.endswith("1") else "43",
        "huggingface_repository": "Mikolinton/sicurre-phishing-fr",
        "huggingface_revision": "candidate-sha-1" if run_id.endswith("1") else "candidate-sha-2",
        "training_github_run_id": "29658891850" if run_id.endswith("1") else "29658891851",
        "training_dataset_version_tag": "base-20260718-144342",
    }


def evaluation_payload(run_id: str = "mlflow-candidate-1") -> dict[str, object]:
    """Build a passing provisional non-regression result."""
    return {
        "candidate_mlflow_run_id": run_id,
        "incumbent_huggingface_revision": None,
        "evaluation_set_version_tag": "golden-20260719-v1",
        "evaluation_set_checksum": CHECKSUM,
        "mlflow_evaluation_run_id": f"golden-eval-{run_id}",
        "outcome": "passed",
        "metrics": {
            "candidate_weighted_f1": 0.94,
            "production_weighted_f1": 0.93,
            "candidate_phishing_recall": 0.98,
            "production_phishing_recall": 0.97,
            "candidate_legitimate_false_positives": 1,
            "production_legitimate_false_positives": 2,
        },
        "evaluated_at": NOW,
    }


async def prepare_candidate(
    client: AsyncClient, frozen_dataset: DataDataset, run_id: str = "mlflow-candidate-1"
) -> None:
    """Register the approved set, candidate, and passing evaluation."""
    del frozen_dataset
    for path, payload in (
        ("/internal/ml/evaluation-sets", evaluation_set_payload()),
        ("/internal/ml/candidates", candidate_payload(run_id)),
        ("/internal/ml/evaluations", evaluation_payload(run_id)),
    ):
        response = await client.post(path, headers=AUTH_HEADERS, json=payload)
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_internal_model_callbacks_require_service_auth(client: AsyncClient) -> None:
    """Customer requests cannot write model-governance records."""
    response = await client.post("/internal/ml/evaluation-sets", json=evaluation_set_payload())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_candidate_and_evaluation_callbacks_are_idempotent(
    client: AsyncClient, frozen_dataset: DataDataset
) -> None:
    """External retries return existing identities and never promote candidates."""
    del frozen_dataset
    first_set = await client.post(
        "/internal/ml/evaluation-sets",
        headers=AUTH_HEADERS,
        json=evaluation_set_payload("draft"),
    )
    approved_set = await client.post(
        "/internal/ml/evaluation-sets",
        headers=AUTH_HEADERS,
        json=evaluation_set_payload(),
    )
    first_candidate = await client.post(
        "/internal/ml/candidates", headers=AUTH_HEADERS, json=candidate_payload()
    )
    replay_candidate = await client.post(
        "/internal/ml/candidates", headers=AUTH_HEADERS, json=candidate_payload()
    )
    first_evaluation = await client.post(
        "/internal/ml/evaluations", headers=AUTH_HEADERS, json=evaluation_payload()
    )
    replay_evaluation = await client.post(
        "/internal/ml/evaluations", headers=AUTH_HEADERS, json=evaluation_payload()
    )

    assert first_set.json()["status"] == "draft"
    assert approved_set.json()["status"] == "approved"
    assert approved_set.json()["idempotent"] is True
    assert first_candidate.json()["status"] == "candidate"
    assert replay_candidate.json()["idempotent"] is True
    assert first_evaluation.json()["status"] == "passed"
    assert replay_evaluation.json()["idempotent"] is True


@pytest.mark.asyncio
async def test_conflicting_candidate_replay_is_rejected(
    client: AsyncClient, frozen_dataset: DataDataset
) -> None:
    """One MLflow run cannot be rebound to another registry version."""
    del frozen_dataset
    payload = candidate_payload()
    assert (
        await client.post("/internal/ml/candidates", headers=AUTH_HEADERS, json=payload)
    ).status_code == 200
    payload["mlflow_model_version"] = "999"
    response = await client.post("/internal/ml/candidates", headers=AUTH_HEADERS, json=payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "candidate_conflict"


@pytest.mark.asyncio
async def test_lineage_callbacks_reject_unknown_or_conflicting_dependencies(
    client: AsyncClient, frozen_dataset: DataDataset
) -> None:
    """Unknown datasets, unapproved sets, and checksum drift fail explicitly."""
    missing_dataset = candidate_payload()
    missing_dataset["training_dataset_version_tag"] = "unknown"
    response = await client.post(
        "/internal/ml/candidates", headers=AUTH_HEADERS, json=missing_dataset
    )
    assert response.json()["detail"]["code"] == "training_dataset_not_found"

    del frozen_dataset
    await client.post("/internal/ml/candidates", headers=AUTH_HEADERS, json=candidate_payload())
    response = await client.post(
        "/internal/ml/evaluations", headers=AUTH_HEADERS, json=evaluation_payload()
    )
    assert response.json()["detail"]["code"] == "approved_evaluation_set_required"
    await client.post(
        "/internal/ml/evaluation-sets",
        headers=AUTH_HEADERS,
        json=evaluation_set_payload(),
    )
    checksum_drift = evaluation_payload()
    checksum_drift["evaluation_set_checksum"] = "c" * 64
    response = await client.post(
        "/internal/ml/evaluations", headers=AUTH_HEADERS, json=checksum_drift
    )
    assert response.json()["detail"]["code"] == "evaluation_set_checksum_mismatch"

    relocated_set = evaluation_set_payload()
    relocated_set["object_uri"] = "r2://replacement-evaluation/golden.jsonl"
    response = await client.post(
        "/internal/ml/evaluation-sets", headers=AUTH_HEADERS, json=relocated_set
    )
    assert response.status_code == 200
    assert response.json()["idempotent"] is True

    conflicting_set = evaluation_set_payload()
    conflicting_set["item_count"] = 61
    conflicting_set["label_counts"] = {"phishing": 26, "legitimate": 25, "spam": 10}
    conflicting_set["language_counts"] = {"fr": 61}
    response = await client.post(
        "/internal/ml/evaluation-sets", headers=AUTH_HEADERS, json=conflicting_set
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_deployment_requires_known_passing_matching_candidate(
    client: AsyncClient, frozen_dataset: DataDataset
) -> None:
    """Manual approval cannot bypass evaluation or immutable artifact identity."""
    unknown = {
        "candidate_mlflow_run_id": "unknown",
        "mlflow_evaluation_run_id": "unknown",
        "github_run_id": "promotion-unknown",
        "approved_by": "owner@sicurre.com",
        "approved_at": NOW,
        "status": "active",
        "deployed_revision": "unknown-sha",
        "deployed_at": NOW,
    }
    response = await client.post("/internal/ml/deployments", headers=AUTH_HEADERS, json=unknown)
    assert response.json()["detail"]["code"] == "promotion_lineage_not_found"

    await prepare_candidate(client, frozen_dataset)
    mismatched = {
        **unknown,
        "candidate_mlflow_run_id": "mlflow-candidate-1",
        "mlflow_evaluation_run_id": "golden-eval-mlflow-candidate-1",
        "github_run_id": "promotion-mismatch",
        "deployed_revision": "different-sha",
    }
    response = await client.post("/internal/ml/deployments", headers=AUTH_HEADERS, json=mismatched)
    assert response.json()["detail"]["code"] == "deployed_revision_mismatch"


@pytest.mark.asyncio
async def test_active_deployment_retires_previous_production(
    client: AsyncClient,
    frozen_dataset: DataDataset,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Manual promotion records one active model and retires its incumbent."""
    await prepare_candidate(client, frozen_dataset)
    first_deployment = {
        "candidate_mlflow_run_id": "mlflow-candidate-1",
        "mlflow_evaluation_run_id": "golden-eval-mlflow-candidate-1",
        "github_run_id": "promotion-run-1",
        "approved_by": "owner@sicurre.com",
        "approved_at": NOW,
        "status": "active",
        "deployed_revision": "candidate-sha-1",
        "deployed_at": NOW,
    }
    response = await client.post(
        "/internal/ml/deployments", headers=AUTH_HEADERS, json=first_deployment
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"

    await prepare_candidate(client, frozen_dataset, "mlflow-candidate-2")
    second_deployment = {
        **first_deployment,
        "candidate_mlflow_run_id": "mlflow-candidate-2",
        "mlflow_evaluation_run_id": "golden-eval-mlflow-candidate-2",
        "github_run_id": "promotion-run-2",
        "deployed_revision": "candidate-sha-2",
    }
    response = await client.post(
        "/internal/ml/deployments", headers=AUTH_HEADERS, json=second_deployment
    )
    assert response.status_code == 200

    async with session_factory() as session:
        models = (await session.execute(select(MlModelVersion))).scalars().all()
        deployments = (await session.execute(select(MlModelDeployment))).scalars().all()
    assert sorted(model.stage for model in models) == ["production", "retired"]
    assert sorted(deployment.status for deployment in deployments) == [
        DeploymentStatus.ACTIVE.value,
        DeploymentStatus.RETIRED.value,
    ]


@pytest.mark.asyncio
async def test_failed_deployment_does_not_promote_candidate(
    client: AsyncClient,
    frozen_dataset: DataDataset,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A failed workflow is auditable while production identity remains unchanged."""
    await prepare_candidate(client, frozen_dataset)
    response = await client.post(
        "/internal/ml/deployments",
        headers=AUTH_HEADERS,
        json={
            "candidate_mlflow_run_id": "mlflow-candidate-1",
            "mlflow_evaluation_run_id": "golden-eval-mlflow-candidate-1",
            "github_run_id": "promotion-failed-1",
            "approved_by": "owner@sicurre.com",
            "approved_at": NOW,
            "status": "failed",
            "failure_reason": "Deployment smoke failed",
        },
    )
    assert response.status_code == 200
    async with session_factory() as session:
        candidate = (await session.execute(select(MlModelVersion))).scalar_one()
    assert candidate.stage == ModelStage.CANDIDATE.value
