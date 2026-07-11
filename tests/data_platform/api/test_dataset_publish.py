"""API-layer tests for POST /datasets/{id}/publish.

Uses in-memory SQLite + ASGI transport. The DatasetPublishService is patched
at the router module level so no real Kaggle/GitHub calls are made.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base, get_async_session
from data_platform.api.main import create_app
from data_platform.services.dataset_publish import (
    DatasetNotFrozenError,
    DatasetPublishConfigError,
    DatasetPublishResult,
    DatasetPublishService,
    GitHubDispatchPublishError,
    KagglePushPublishError,
)
from data_platform.services.shared.github_actions_gateway import GitHubDispatchError
from data_platform.services.shared.kaggle_gateway import KagglePushError
from db.models.lineage import DataDataset, DatasetStatus

AUTH_HEADERS = {"Authorization": "Bearer dev-token"}
UNKNOWN_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as sess:
            yield sess

    app.dependency_overrides[get_async_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def frozen_dataset_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    async with session_factory() as sess:
        dataset = DataDataset(
            name="sicurre-v1",
            version_tag="v1.0.0",
            target_usage="training",
            status=DatasetStatus.FROZEN.value,
            frozen_at=datetime.now(timezone.utc),
            item_count=0,
        )
        sess.add(dataset)
        await sess.commit()
        return str(dataset.id)


@pytest_asyncio.fixture
async def draft_dataset_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    async with session_factory() as sess:
        dataset = DataDataset(
            name="sicurre-draft",
            version_tag="v0.0.1",
            target_usage="training",
            status=DatasetStatus.DRAFT.value,
            item_count=0,
        )
        sess.add(dataset)
        await sess.commit()
        return str(dataset.id)


def _ok_result(
    slug: str = "user/sicurre-data", version: int = 4
) -> DatasetPublishResult:
    return DatasetPublishResult(
        kaggle_url=f"https://www.kaggle.com/datasets/{slug}/versions/{version}",
        kaggle_version_id=version,
        github_dispatch_sent=True,
    )


# ── Happy path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_200_with_result(
    client: AsyncClient,
    frozen_dataset_id: str,
) -> None:
    with patch("data_platform.api.routers.datasets.publish_service") as mock_svc:
        mock_svc.publish = AsyncMock(return_value=_ok_result())
        response = await client.post(
            f"/v1/data/datasets/{frozen_dataset_id}/publish",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["kaggle_version_id"] == 4
    assert body["github_dispatch_sent"] is True
    assert "kaggle.com" in body["kaggle_url"]


# ── 404 ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_404_for_unknown_dataset(
    client: AsyncClient,
) -> None:
    from db.queries.records import DatasetNotFoundError

    with patch("data_platform.api.routers.datasets.publish_service") as mock_svc:
        mock_svc.publish = AsyncMock(
            side_effect=DatasetNotFoundError(uuid.UUID(UNKNOWN_ID))
        )
        response = await client.post(
            f"/v1/data/datasets/{UNKNOWN_ID}/publish",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 404


# ── 409 ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_409_when_not_frozen(
    client: AsyncClient,
    draft_dataset_id: str,
) -> None:
    with patch("data_platform.api.routers.datasets.publish_service") as mock_svc:
        mock_svc.publish = AsyncMock(side_effect=DatasetNotFrozenError("not frozen"))
        response = await client.post(
            f"/v1/data/datasets/{draft_dataset_id}/publish",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 409
    assert "FROZEN" in response.json()["detail"]


# ── 503 ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_503_when_not_configured(
    client: AsyncClient,
    frozen_dataset_id: str,
) -> None:
    with patch("data_platform.api.routers.datasets.publish_service") as mock_svc:
        mock_svc.publish = AsyncMock(
            side_effect=DatasetPublishConfigError("missing secrets")
        )
        response = await client.post(
            f"/v1/data/datasets/{frozen_dataset_id}/publish",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 503


# ── 502 Kaggle failure ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_502_on_kaggle_failure(
    client: AsyncClient,
    frozen_dataset_id: str,
) -> None:
    with patch("data_platform.api.routers.datasets.publish_service") as mock_svc:
        mock_svc.publish = AsyncMock(
            side_effect=KagglePushPublishError(KagglePushError("CLI exited 1"))
        )
        response = await client.post(
            f"/v1/data/datasets/{frozen_dataset_id}/publish",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 502
    assert "Kaggle push failed" in response.json()["detail"]


# ── 502 GitHub failure ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_502_on_github_dispatch_failure(
    client: AsyncClient,
    frozen_dataset_id: str,
) -> None:
    with patch("data_platform.api.routers.datasets.publish_service") as mock_svc:
        mock_svc.publish = AsyncMock(
            side_effect=GitHubDispatchPublishError(
                GitHubDispatchError("HTTP 403"),
                kaggle_version_id=5,
                kaggle_slug="user/sicurre-data",
            )
        )
        response = await client.post(
            f"/v1/data/datasets/{frozen_dataset_id}/publish",
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 502
    body = response.json()
    assert "5" in body["detail"]
    assert "GitHub" in body["detail"]


# ── Auth guard ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_requires_authentication(
    client: AsyncClient,
    frozen_dataset_id: str,
) -> None:
    response = await client.post(f"/v1/data/datasets/{frozen_dataset_id}/publish")
    assert response.status_code == 401


# ── Response shape — no internal leakage ─────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_response_contains_no_token(
    client: AsyncClient,
    frozen_dataset_id: str,
) -> None:
    """Ensure no secret values leak into the HTTP response."""
    with patch("data_platform.api.routers.datasets.publish_service") as mock_svc:
        mock_svc.publish = AsyncMock(return_value=_ok_result())
        response = await client.post(
            f"/v1/data/datasets/{frozen_dataset_id}/publish",
            headers=AUTH_HEADERS,
        )

    body = response.text
    assert "ghp_" not in body
    assert "KGAT_" not in body
    assert "token" not in body.lower() or "github_dispatch" not in body.lower()
