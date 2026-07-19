"""Integration tests for DatasetPublishService.

Uses in-memory SQLite with real DB operations.
Gateways (Kaggle, GitHub) are replaced with async stubs — no real HTTP or CLI calls.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.services.dataset_publish import (
    DatasetNotFrozenError,
    DatasetPublishConfigError,
    DatasetPublishService,
    GitHubDispatchPublishError,
    KagglePushPublishError,
)
from data_platform.services.shared.github_actions_gateway import (
    GitHubActionsGateway,
    GitHubDispatchError,
)
from data_platform.services.shared.kaggle_gateway import KaggleGateway, KagglePushError
from db.models.lineage import DataDataset, DatasetStatus

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as sess:
        yield sess

    await engine.dispose()


def _full_settings() -> MagicMock:
    """Mock settings with all publish secrets — env-independent."""
    s = MagicMock()
    s.kaggle_username = "testuser"
    s.kaggle_key = "testkey"
    s.kaggle_dataset_slug = "testuser/sicurre-data"
    s.github_ml_repo_owner = "owner"
    s.github_ml_dispatch_token = "ghp_test"
    s.github_ml_repo_name = "sicurre-ml"
    return s


def _missing_settings() -> MagicMock:
    """Mock settings with no publish secrets."""
    s = MagicMock()
    s.kaggle_username = None
    s.kaggle_key = None
    s.kaggle_dataset_slug = None
    s.github_ml_repo_owner = None
    s.github_ml_dispatch_token = None
    s.github_ml_repo_name = "sicurre-ml"
    return s


async def _insert_frozen_dataset(session: AsyncSession) -> DataDataset:
    dataset = DataDataset(
        name="sicurre-v1",
        version_tag="v1.0.0",
        target_usage="training",
        status=DatasetStatus.FROZEN.value,
        frozen_at=datetime.now(UTC),
        item_count=0,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return dataset


async def _insert_draft_dataset(session: AsyncSession) -> DataDataset:
    dataset = DataDataset(
        name="sicurre-draft",
        version_tag="v0.0.1",
        target_usage="training",
        status=DatasetStatus.DRAFT.value,
        item_count=0,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return dataset


# ── _require_secrets ──────────────────────────────────────────────────────────


def test_require_secrets_raises_when_missing() -> None:
    svc = DatasetPublishService(settings=_missing_settings())
    with pytest.raises(DatasetPublishConfigError) as exc_info:
        svc._require_secrets()
    msg = str(exc_info.value)
    assert "KAGGLE_USERNAME" in msg
    assert "SICURRE_GITHUB_ML_DISPATCH_TOKEN" in msg


def test_require_secrets_returns_gateways_when_configured() -> None:
    svc = DatasetPublishService(settings=_full_settings())
    kaggle_gw, github_gw = svc._require_secrets()
    assert isinstance(kaggle_gw, KaggleGateway)
    assert isinstance(github_gw, GitHubActionsGateway)


# ── publish — happy path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_returns_result_on_success(session: AsyncSession) -> None:
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.return_value = 3

    github_stub = AsyncMock(spec=GitHubActionsGateway)
    github_stub.dispatch_training.return_value = None

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        result = await svc.publish(session, dataset.id)

    assert result.github_dispatch_sent is True
    assert result.kaggle_version_id == 3
    assert "testuser/sicurre-data" in result.kaggle_url
    assert "3" in result.kaggle_url
    await session.refresh(dataset)
    assert dataset.content_checksum is not None
    assert len(dataset.content_checksum) == 64
    assert dataset.schema_version == "1"
    github_stub.dispatch_training.assert_awaited_once_with(
        kaggle_slug="testuser/sicurre-data",
        dataset_id=str(dataset.id),
        dataset_version="v1.0.0",
        dataset_sha256=dataset.content_checksum,
    )


@pytest.mark.asyncio
async def test_publish_uses_dataset_root_when_kaggle_omits_version(
    session: AsyncSession,
) -> None:
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())
    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.return_value = 0
    github_stub = AsyncMock(spec=GitHubActionsGateway)

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        result = await svc.publish(session, dataset.id)

    assert result.kaggle_url == "https://www.kaggle.com/datasets/testuser/sicurre-data"


@pytest.mark.asyncio
async def test_publish_writes_kaggle_version_to_db(session: AsyncSession) -> None:
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.return_value = 7
    github_stub = AsyncMock(spec=GitHubActionsGateway)
    github_stub.dispatch_training.return_value = None

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        await svc.publish(session, dataset.id)

    await session.refresh(dataset)
    assert dataset.kaggle_version_id == 7
    assert dataset.published_at is not None


@pytest.mark.asyncio
async def test_publish_passes_version_tag_to_kaggle_message(
    session: AsyncSession,
) -> None:
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.return_value = 1
    github_stub = AsyncMock(spec=GitHubActionsGateway)
    github_stub.dispatch_training.return_value = None

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        await svc.publish(session, dataset.id)

    call_kwargs = kaggle_stub.push_version.call_args[1]
    assert "v1.0.0" in call_kwargs["message"]


# ── publish — dataset not found ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_raises_not_found_for_unknown_id(
    session: AsyncSession,
) -> None:
    from db.queries.records import DatasetNotFoundError

    svc = DatasetPublishService(settings=_full_settings())
    kaggle_stub = AsyncMock(spec=KaggleGateway)
    github_stub = AsyncMock(spec=GitHubActionsGateway)

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        with pytest.raises(DatasetNotFoundError):
            await svc.publish(session, uuid.uuid4())


# ── publish — not frozen ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_raises_when_dataset_not_frozen(
    session: AsyncSession,
) -> None:
    dataset = await _insert_draft_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    github_stub = AsyncMock(spec=GitHubActionsGateway)

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        with pytest.raises(DatasetNotFrozenError):
            await svc.publish(session, dataset.id)

    kaggle_stub.push_version.assert_not_called()


# ── publish — kaggle failure ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_raises_kaggle_error_and_no_github_call(
    session: AsyncSession,
) -> None:
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.side_effect = KagglePushError("CLI exited 1: not found")
    github_stub = AsyncMock(spec=GitHubActionsGateway)

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        with pytest.raises(KagglePushPublishError):
            await svc.publish(session, dataset.id)

    github_stub.dispatch_training.assert_not_called()


@pytest.mark.asyncio
async def test_publish_kaggle_failure_leaves_db_unpublished(
    session: AsyncSession,
) -> None:
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.side_effect = KagglePushError("err")
    github_stub = AsyncMock(spec=GitHubActionsGateway)

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        with pytest.raises(KagglePushPublishError):
            await svc.publish(session, dataset.id)

    await session.refresh(dataset)
    assert dataset.kaggle_version_id is None
    assert dataset.published_at is None


# ── publish — github dispatch failure ────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_raises_github_error_with_kaggle_version_id(
    session: AsyncSession,
) -> None:
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.return_value = 5
    github_stub = AsyncMock(spec=GitHubActionsGateway)
    github_stub.dispatch_training.side_effect = GitHubDispatchError("HTTP 403")

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        with pytest.raises(GitHubDispatchPublishError) as exc_info:
            await svc.publish(session, dataset.id)

    assert exc_info.value.kaggle_version_id == 5
    assert exc_info.value.kaggle_slug == "testuser/sicurre-data"


@pytest.mark.asyncio
async def test_publish_github_failure_still_writes_db(
    session: AsyncSession,
) -> None:
    """DB is written (best-effort) before GitHub dispatch — so it should be set
    even if GitHub later fails."""
    dataset = await _insert_frozen_dataset(session)
    svc = DatasetPublishService(settings=_full_settings())

    kaggle_stub = AsyncMock(spec=KaggleGateway)
    kaggle_stub.push_version.return_value = 2
    github_stub = AsyncMock(spec=GitHubActionsGateway)
    github_stub.dispatch_training.side_effect = GitHubDispatchError("err")

    with patch.object(svc, "_require_secrets", return_value=(kaggle_stub, github_stub)):
        with pytest.raises(GitHubDispatchPublishError):
            await svc.publish(session, dataset.id)

    await session.refresh(dataset)
    assert dataset.kaggle_version_id == 2
    assert dataset.published_at is not None


# ── publish — missing config ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_raises_config_error_before_db_access(
    session: AsyncSession,
) -> None:
    """Config check runs before any DB access — no dataset needed."""
    svc = DatasetPublishService(settings=_missing_settings())

    with pytest.raises(DatasetPublishConfigError):
        await svc.publish(session, uuid.uuid4())
