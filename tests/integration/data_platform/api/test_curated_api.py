from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base, get_async_session
from db.models import (
    DataAnnotation,
    DataDataset,
    DataDatasetItem,
    DataIngestionRun,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
)
from db.queries import DuplicateDatasetError
from db.services import DatasetService
from data_platform.api.main import create_app


AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


def utc_timestamp() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

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
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    async with session_factory() as session:
        source = DataSourceSystem(name="seed-source", source_type="file")
        session.add(source)
        await session.flush()

        ingestion = DataIngestionRun(
            source_system_id=source.id,
            started_at=utc_timestamp(),
            status="completed",
            trigger_mode="manual",
        )
        session.add(ingestion)
        await session.flush()

        raw_object = DataRawObject(
            ingestion_run_id=ingestion.id,
            object_type="file",
            content_hash="seed-hash",
            source_metadata={},
            collected_at=utc_timestamp(),
        )
        session.add(raw_object)
        await session.flush()

        raw_record = DataRawRecord(
            raw_object_id=raw_object.id,
            record_key="row-1",
            raw_content="Bonjour ceci est un email brut",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        session.add(raw_record)

        processing_run = DataProcessingRun(
            pipeline_version="v1",
            started_at=utc_timestamp(),
            status="completed",
        )
        session.add(processing_run)
        await session.flush()

        message = DataNormalizedMessage(
            raw_record=raw_record,
            processing_run=processing_run,
            normalized_text="Email normalise seed",
            text_sha256="seed-message-hash",
            language="fr",
            current_label="phishing",
            text_length=20,
            normalized_at=utc_timestamp(),
        )
        session.add(message)
        await session.flush()

        dataset = DataDataset(
            name="seed-dataset",
            version_tag="seed-v1",
            target_usage="training",
            status="draft",
        )
        session.add(dataset)
        await session.flush()

        dataset_item = DataDatasetItem(
            dataset_id=dataset.id,
            normalized_message_id=message.id,
            split_name="train",
            sample_weight=1.0,
            row_order=1,
        )
        session.add(dataset_item)
        await session.commit()

        return {
            "source_id": str(source.id),
            "raw_record_id": str(raw_record.id),
            "processing_run_id": str(processing_run.id),
            "message_id": str(message.id),
            "dataset_id": str(dataset.id),
        }


@pytest.mark.asyncio
async def test_list_raw_records_with_filters(
    client: AsyncClient, seeded_ids: dict[str, str]
) -> None:
    response = await client.get(
        "/v1/data/raw-records",
        headers=AUTH_HEADERS,
        params={
            "source_system_id": seeded_ids["source_id"],
            "language": "fr",
            "is_usable": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == seeded_ids["raw_record_id"]


@pytest.mark.asyncio
async def test_message_crud_flow(
    client: AsyncClient, seeded_ids: dict[str, str]
) -> None:
    create_response = await client.post(
        "/v1/data/messages",
        headers=AUTH_HEADERS,
        json={
            "raw_record_id": seeded_ids["raw_record_id"],
            "processing_run_id": seeded_ids["processing_run_id"],
            "normalized_text": "Deuxieme message normalise",
            "language": "fr",
            "current_label": "spam",
            "redaction_status": "not_required",
        },
    )

    assert create_response.status_code == 201
    message_id = create_response.json()["id"]
    assert create_response.json()["contains_pii"] is False

    list_response = await client.get(
        "/v1/data/messages",
        headers=AUTH_HEADERS,
        params={"label": "spam"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    get_response = await client.get(
        f"/v1/data/messages/{message_id}",
        headers=AUTH_HEADERS,
    )
    assert get_response.status_code == 200
    assert get_response.json()["current_label"] == "spam"

    patch_response = await client.patch(
        f"/v1/data/messages/{message_id}",
        headers=AUTH_HEADERS,
        json={"current_label": "legitimate", "redaction_status": "redacted"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["current_label"] == "legitimate"
    assert patch_response.json()["redaction_status"] == "redacted"

    delete_response = await client.delete(
        f"/v1/data/messages/{message_id}",
        headers=AUTH_HEADERS,
    )
    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_create_annotation(
    client: AsyncClient, seeded_ids: dict[str, str]
) -> None:
    response = await client.post(
        "/v1/data/annotations",
        headers=AUTH_HEADERS,
        json={
            "normalized_message_id": seeded_ids["message_id"],
            "label": "phishing",
            "label_source": "manual_review",
            "confidence": 0.95,
            "annotated_at": "2026-03-17T10:00:00Z",
        },
    )

    assert response.status_code == 201
    assert response.json()["normalized_message_id"] == seeded_ids["message_id"]


@pytest.mark.asyncio
async def test_list_and_create_datasets(
    client: AsyncClient, seeded_ids: dict[str, str]
) -> None:
    list_response = await client.get("/v1/data/datasets", headers=AUTH_HEADERS)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    items_response = await client.get(
        f"/v1/data/datasets/{seeded_ids['dataset_id']}/items",
        headers=AUTH_HEADERS,
    )
    assert items_response.status_code == 200
    assert items_response.json()["total"] == 1
    assert (
        items_response.json()["items"][0]["normalized_message_id"]
        == seeded_ids["message_id"]
    )

    create_response = await client.post(
        "/v1/data/datasets",
        headers=AUTH_HEADERS,
        json={
            "name": "second-dataset",
            "version_tag": "second-v1",
            "target_usage": "training",
            "status": "draft",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["version_tag"] == "second-v1"


@pytest.mark.asyncio
async def test_create_message_redacts_pii(
    client: AsyncClient, seeded_ids: dict[str, str]
) -> None:
    response = await client.post(
        "/v1/data/messages",
        headers=AUTH_HEADERS,
        json={
            "raw_record_id": seeded_ids["raw_record_id"],
            "processing_run_id": seeded_ids["processing_run_id"],
            "normalized_text": "Contactez jean.dupont@example.com ou visitez https://evil.test/offre-maintenance pour finaliser votre dossier immédiatement.",
            "language": "fr",
            "current_label": "phishing",
            "redaction_status": "not_required",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert "[EMAIL]" in payload["normalized_text"]
    assert "[URL]" in payload["normalized_text"]
    assert payload["contains_pii"] is True


@pytest.mark.asyncio
async def test_build_dataset_from_annotated_messages(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        source = DataSourceSystem(name="builder-source", source_type="file")
        session.add(source)
        await session.flush()

        ingestion = DataIngestionRun(
            source_system_id=source.id,
            started_at=utc_timestamp(),
            status="completed",
            trigger_mode="manual",
        )
        session.add(ingestion)
        await session.flush()

        raw_object = DataRawObject(
            ingestion_run_id=ingestion.id,
            object_type="file",
            content_hash="builder-hash",
            source_metadata={},
            collected_at=utc_timestamp(),
        )
        session.add(raw_object)

        processing_run = DataProcessingRun(
            pipeline_version="v1",
            started_at=utc_timestamp(),
            status="completed",
        )
        session.add(processing_run)
        await session.flush()

        message_counter = 0
        for label in ["phishing", "spam", "legitimate"]:
            for _ in range(10):
                message_counter += 1
                raw_record = DataRawRecord(
                    raw_object_id=raw_object.id,
                    record_key=f"builder-row-{message_counter}",
                    raw_content=f"Contenu brut {message_counter}",
                    detected_language="fr",
                    is_usable=True,
                    extracted_at=utc_timestamp(),
                )
                message = DataNormalizedMessage(
                    raw_record=raw_record,
                    processing_run=processing_run,
                    normalized_text=f"Message normalise {message_counter}",
                    text_sha256=f"builder-message-hash-{message_counter:03d}",
                    language="fr",
                    current_label=label,
                    text_length=24,
                    normalized_at=utc_timestamp(),
                )
                session.add_all(
                    [
                        raw_record,
                        message,
                        DataAnnotation(
                            normalized_message=message,
                            label=label,
                            label_source="manual_review",
                            confidence=1.0,
                            annotated_at=utc_timestamp(),
                        ),
                    ]
                )

        extra_raw_record = DataRawRecord(
            raw_object_id=raw_object.id,
            record_key="builder-row-unannotated",
            raw_content="Contenu brut sans annotation",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        extra_message = DataNormalizedMessage(
            raw_record=extra_raw_record,
            processing_run=processing_run,
            normalized_text="Message sans annotation",
            text_sha256="builder-message-hash-unannotated",
            language="fr",
            current_label="phishing",
            text_length=24,
            normalized_at=utc_timestamp(),
        )
        session.add_all([extra_raw_record, extra_message])
        await session.commit()

        service = DatasetService()
        result = await service.build(
            session,
            name="curated-training",
            version_tag="curated-training-v1",
            target_usage="training",
            status="frozen",
        )

        assert result.dataset.item_count == 30
        assert result.split_counts == {"train": 24, "val": 3, "test": 3}
        assert result.dataset.frozen_at is not None

        items, total = await service.list_items(
            session,
            result.dataset.id,
            limit=100,
            offset=0,
        )
        assert total == 30
        assert [item.row_order for item in items] == list(range(1, 31))
        assert {item.split_name for item in items} == {"train", "val", "test"}


@pytest.mark.asyncio
async def test_build_dataset_rejects_duplicate_version_tag(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        source = DataSourceSystem(name="duplicate-builder-source", source_type="file")
        session.add(source)
        await session.flush()

        ingestion = DataIngestionRun(
            source_system_id=source.id,
            started_at=utc_timestamp(),
            status="completed",
            trigger_mode="manual",
        )
        session.add(ingestion)
        await session.flush()

        raw_object = DataRawObject(
            ingestion_run_id=ingestion.id,
            object_type="file",
            content_hash="duplicate-builder-hash",
            source_metadata={},
            collected_at=utc_timestamp(),
        )
        processing_run = DataProcessingRun(
            pipeline_version="v1",
            started_at=utc_timestamp(),
            status="completed",
        )
        raw_record = DataRawRecord(
            raw_object=raw_object,
            record_key="duplicate-builder-row",
            raw_content="Contenu brut duplicate",
            detected_language="fr",
            is_usable=True,
            extracted_at=utc_timestamp(),
        )
        message = DataNormalizedMessage(
            raw_record=raw_record,
            processing_run=processing_run,
            normalized_text="Message duplicate",
            text_sha256="duplicate-builder-message-hash",
            language="fr",
            current_label="phishing",
            text_length=17,
            normalized_at=utc_timestamp(),
        )
        annotation = DataAnnotation(
            normalized_message=message,
            label="phishing",
            label_source="manual_review",
            confidence=1.0,
            annotated_at=utc_timestamp(),
        )
        session.add_all([raw_object, processing_run, raw_record, message, annotation])
        await session.commit()

        service = DatasetService()
        await service.build(
            session,
            name="duplicate-dataset",
            version_tag="duplicate-dataset-v1",
            target_usage="training",
            status="draft",
        )

        with pytest.raises(DuplicateDatasetError):
            await service.build(
                session,
                name="duplicate-dataset",
                version_tag="duplicate-dataset-v1",
                target_usage="training",
                status="draft",
            )
