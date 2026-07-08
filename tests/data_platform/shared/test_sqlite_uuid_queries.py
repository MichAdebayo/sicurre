"""Regression coverage for mixed UUID string storage in SQLite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from db.queries.records import DatasetQueries, NormalizedMessageQueries


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


@pytest.mark.asyncio
async def test_dataset_export_join_matches_hyphenated_and_hex_uuid_storage(
    session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    source_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    run_id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    raw_object_id = "cccccccccccccccccccccccccccccccc"
    raw_record_id = "dddddddddddddddddddddddddddddddd"
    processing_run_id = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    dataset_id = UUID("22222222-2222-2222-2222-222222222222")
    normalized_hyphenated = "11111111-1111-1111-1111-111111111111"
    normalized_hex = "11111111111111111111111111111111"

    await session.execute(
        text(
            """
            INSERT INTO data_source_system
                (id, name, source_type, contains_personal_data, is_active, created_at)
            VALUES
                (:id, 'mixed-uuid-source', 'manual', 0, 1, :now)
            """
        ),
        {"id": source_id, "now": now},
    )
    await session.execute(
        text(
            """
            INSERT INTO data_ingestion_run
                (id, source_system_id, started_at, status, trigger_mode,
                 raw_object_count, raw_record_count, created_at)
            VALUES
                (:id, :source_id, :now, 'completed', 'manual', 1, 1, :now)
            """
        ),
        {"id": run_id, "source_id": source_id, "now": now},
    )
    await session.execute(
        text(
            """
            INSERT INTO data_raw_object
                (id, ingestion_run_id, object_type, content_hash,
                 source_metadata, collected_at, created_at)
            VALUES
                (:id, :run_id, 'file', 'hash-mixed-uuid', '{}', :now, :now)
            """
        ),
        {"id": raw_object_id, "run_id": run_id, "now": now},
    )
    await session.execute(
        text(
            """
            INSERT INTO data_raw_record
                (id, raw_object_id, record_key, raw_content, is_usable,
                 extracted_at, created_at)
            VALUES
                (:id, :raw_object_id, 'record-1', 'raw', 1, :now, :now)
            """
        ),
        {"id": raw_record_id, "raw_object_id": raw_object_id, "now": now},
    )
    await session.execute(
        text(
            """
            INSERT INTO data_processing_run
                (id, pipeline_version, started_at, status, normalized_count,
                 rejected_count, created_at)
            VALUES
                (:id, 'test', :now, 'completed', 1, 0, :now)
            """
        ),
        {"id": processing_run_id, "now": now},
    )
    await session.execute(
        text(
            """
            INSERT INTO data_normalized_message
                (id, raw_record_id, processing_run_id, normalized_text, text_sha256,
                 language, current_label, contains_pii, redaction_status,
                 text_length, normalized_at, created_at)
            VALUES
                (:id, :raw_record_id, :processing_run_id,
                 'Bonjour test phishing', 'sha-mixed-uuid', 'fr', 'phishing',
                 0, 'not_required', 21, :now, :now)
            """
        ),
        {
            "id": normalized_hyphenated,
            "raw_record_id": raw_record_id,
            "processing_run_id": processing_run_id,
            "now": now,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO data_dataset
                (id, name, version_tag, target_usage, status, item_count, created_at)
            VALUES
                (:id, 'mixed-uuid-dataset', 'mixed-uuid-v1',
                 'training', 'frozen', 1, :now)
            """
        ),
        {"id": dataset_id.hex, "now": now},
    )
    await session.execute(
        text(
            """
            INSERT INTO data_dataset_item
                (id, dataset_id, normalized_message_id, split_name,
                 sample_weight, row_order, created_at)
            VALUES
                ('33333333333333333333333333333333', :dataset_id,
                 :normalized_message_id, 'train', 1.0, 1, :now)
            """
        ),
        {
            "dataset_id": dataset_id.hex,
            "normalized_message_id": normalized_hex,
            "now": now,
        },
    )
    await session.commit()

    export_rows = await DatasetQueries().list_items_for_export(
        session,
        dataset_id,
        split_name="train",
    )
    messages, total = await NormalizedMessageQueries().list(
        session,
        label=None,
        language=None,
        split="train",
        limit=10,
        offset=0,
    )

    assert export_rows == [("Bonjour test phishing", "phishing")]
    assert total == 1
    assert len(messages) == 1
