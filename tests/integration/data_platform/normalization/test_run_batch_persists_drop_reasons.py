"""run_batch writes the drop reason to the row it drops."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.services.shared.normalization_pipeline import NormalizationPipeline

SOURCE_ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
RUN_ID = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
OBJECT_ID = "cccccccccccccccccccccccccccccccc"


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as sess:
        yield sess
    await engine.dispose()


async def _seed_source(session: AsyncSession, source_name: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text(
            "INSERT INTO data_source_system (id, name, source_type,"
            " contains_personal_data, is_active, created_at)"
            " VALUES (:id, :name, 'file', 0, 1, :now)"
        ),
        {"id": SOURCE_ID, "name": source_name, "now": now},
    )
    await session.execute(
        text(
            "INSERT INTO data_ingestion_run (id, source_system_id, started_at, status,"
            " trigger_mode, raw_object_count, raw_record_count, created_at)"
            " VALUES (:id, :source_id, :now, 'completed', 'manual', 1, 1, :now)"
        ),
        {"id": RUN_ID, "source_id": SOURCE_ID, "now": now},
    )
    await session.execute(
        text(
            "INSERT INTO data_raw_object (id, ingestion_run_id, object_type,"
            " content_hash, source_metadata, collected_at, created_at)"
            " VALUES (:id, :run_id, 'file', 'h', '{}', :now, :now)"
        ),
        {"id": OBJECT_ID, "run_id": RUN_ID, "now": now},
    )


async def _add_raw_record(session: AsyncSession, record_id: str, payload: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text(
            # detected_language must be 'fr': run_batch isolates the French lane in its selection query, s
            "INSERT INTO data_raw_record (id, raw_object_id, source_system_id,"
            " record_key, raw_content, is_usable, detected_language,"
            " extracted_at, created_at)"
            " VALUES (:id, :object_id, :source_id, :key, :content, 1, 'fr',"
            " :now, :now)"
        ),
        {
            "id": record_id,
            "object_id": OBJECT_ID,
            "source_id": SOURCE_ID,
            "key": record_id,
            "content": json.dumps(payload),
            "now": now,
        },
    )


async def _reason(session: AsyncSession, record_id: str) -> str | None:
    result = await session.execute(
        text("SELECT rejection_reason FROM data_raw_record WHERE id = :id"),
        {"id": record_id},
    )
    return result.scalar()


@pytest.mark.asyncio
async def test_a_routing_rejection_names_the_route_outcome(session: AsyncSession) -> None:
    """Routing runs before the content checks, and says so in the reason."""
    await _seed_source(session, "sap-labs-blog")
    await _add_raw_record(session, "d" * 32, {"subject": "", "body": "", "label": "phishing"})
    await session.commit()

    pipeline = NormalizationPipeline(session=session)
    result = await pipeline.run_batch(source_system_name="sap-labs-blog")

    assert await _reason(session, "d" * 32) == "route:rejected"
    assert result["skipped"] == 1 and result["normalized"] == 0


@pytest.mark.asyncio
async def test_a_record_without_a_label_is_dropped_with_its_reason(
    session: AsyncSession,
) -> None:
    await _seed_source(session, "sap-labs-blog")
    await _add_raw_record(
        session,
        "e" * 32,
        {"subject": "Bonjour", "body": "Voici un message en francais.", "label": None},
    )
    await session.commit()

    pipeline = NormalizationPipeline(session=session)
    await pipeline.run_batch(source_system_name="sap-labs-blog")

    assert await _reason(session, "e" * 32) == "no_label"


@pytest.mark.asyncio
async def test_a_duplicate_is_dropped_naming_the_hash_that_matched(
    session: AsyncSession,
) -> None:
    """The second copy is dropped; the first is kept."""
    await _seed_source(session, "sap-labs-blog")
    body = {
        "subject": "Confirmation de commande",
        "body": "Votre commande a bien ete enregistree, merci de votre confiance.",
        "label": "legitimate",
    }
    await _add_raw_record(session, "1" * 32, dict(body))
    await _add_raw_record(session, "2" * 32, dict(body))
    await session.commit()

    pipeline = NormalizationPipeline(session=session)
    await pipeline.run_batch(source_system_name="sap-labs-blog")

    reasons = {await _reason(session, "1" * 32), await _reason(session, "2" * 32)}
    assert "duplicate_text_sha256" in reasons
    assert None in reasons, "exactly one of the pair must survive"


@pytest.mark.asyncio
async def test_an_extraction_failure_records_the_class_and_not_the_message(
    session: AsyncSession,
) -> None:
    """An exception string can carry a fragment of the mail that caused it."""
    await _seed_source(session, "sap-labs-blog")
    now = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text(
            "INSERT INTO data_raw_record (id, raw_object_id, source_system_id,"
            " record_key, raw_content, is_usable, detected_language,"
            " extracted_at, created_at)"
            " VALUES (:id, :object_id, :source_id, 'broken', 'not json at all',"
            " 1, 'fr', :now, :now)"
        ),
        {"id": "f" * 32, "object_id": OBJECT_ID, "source_id": SOURCE_ID, "now": now},
    )
    await session.commit()

    pipeline = NormalizationPipeline(session=session)
    await pipeline.run_batch(source_system_name="sap-labs-blog")

    reason = await _reason(session, "f" * 32)
    assert reason is not None and reason.startswith("extract_error:")
    assert "not json at all" not in reason
