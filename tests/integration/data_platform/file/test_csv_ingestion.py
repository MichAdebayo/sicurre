from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from data_platform.base_ingest.file.parsers.csv_ingestion import ingest_csv_file
from db.models import DataIngestionRun, DataRawRecord, DataSourceSystem
from db.queries import IngestionRunQueries, SourceSystemQueries


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_csv_file_skips_invalid_schema_with_error_log(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    file_path = tmp_path / "invalid_multilingual.csv"
    file_path.write_text(
        "labels,text,text_fr\nspam,Hello world,Bonjour le monde\n",
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)

    async with session_factory() as session:
        result = await ingest_csv_file(
            file_path,
            session,
            SourceSystemQueries(),
            IngestionRunQueries(),
        )
        source_systems = list((await session.scalars(select(DataSourceSystem))).all())
        ingestion_runs = list((await session.scalars(select(DataIngestionRun))).all())
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.inserted_count == 0
    assert result.status == "skipped_invalid_schema"
    assert not source_systems
    assert not ingestion_runs
    assert not raw_records
    assert "required CSV columns are missing: label" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_name", "expected_source_name"),
    [
        ("data-en-hi-de-fr.csv", "data-en-hi-de-fr"),
        ("kaggle_multilingual_spam.csv", "kaggle_multilingual_spam"),
    ],
)
async def test_ingest_csv_file_accepts_historical_multilingual_schema(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    file_name: str,
    expected_source_name: str,
) -> None:
    file_path = tmp_path / file_name
    file_path.write_text(
        (
            "labels,text,text_hi,text_de,text_fr\n"
            "ham,Hello world,Bonjour monde hi,Hallo Welt,Bonjour le monde\n"
            "spam,Hello world,Bonjour monde hi,Hallo Welt,Bonjour le monde\n"
        ),
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)

    async with session_factory() as session:
        result = await ingest_csv_file(
            file_path,
            session,
            SourceSystemQueries(),
            IngestionRunQueries(),
        )
        source_systems = list((await session.scalars(select(DataSourceSystem))).all())
        ingestion_runs = list((await session.scalars(select(DataIngestionRun))).all())
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.inserted_count == 1
    assert result.status == "ingested"
    assert [source_system.name for source_system in source_systems] == [
        expected_source_name
    ]
    assert len(ingestion_runs) == 1
    assert len(raw_records) == 1
    payload = json.loads(raw_records[0].raw_content)
    assert payload["text"] == "Hello world"
    assert payload["label"] == ""
    assert payload["source"] == expected_source_name
    assert payload["language"] is None
    assert raw_records[0].detected_language is None
    assert raw_records[0].source_system_id == source_systems[0].id
    assert "historical multilingual schema" in caplog.text


@pytest.mark.asyncio
async def test_ingest_csv_file_accepts_missing_optional_columns_with_warning(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    file_path = tmp_path / "valid_without_language.csv"
    file_path.write_text(
        "text,label,source\nBonjour,spam,csv_missing_language\n",
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)

    async with session_factory() as session:
        result = await ingest_csv_file(
            file_path,
            session,
            SourceSystemQueries(),
            IngestionRunQueries(),
        )
        source_systems = list((await session.scalars(select(DataSourceSystem))).all())
        ingestion_runs = list((await session.scalars(select(DataIngestionRun))).all())
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.inserted_count == 1
    assert result.status == "ingested"
    assert [source_system.name for source_system in source_systems] == [
        "csv_missing_language"
    ]
    assert len(ingestion_runs) == 1
    assert len(raw_records) == 1
    assert raw_records[0].source_system_id == source_systems[0].id
    assert "missing optional columns: language" in caplog.text


@pytest.mark.asyncio
async def test_ingest_csv_file_respects_trigger_mode(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "scheduled.csv"
    file_path.write_text(
        "text,label,source,language\nBonjour,spam,csv_trigger_mode,fr\n",
        encoding="utf-8",
    )

    async with session_factory() as session:
        result = await ingest_csv_file(
            file_path,
            session,
            SourceSystemQueries(),
            IngestionRunQueries(),
            trigger_mode="scheduled",
        )
        ingestion_run = await session.scalar(select(DataIngestionRun))

    assert result.status == "ingested"
    assert ingestion_run is not None
    assert ingestion_run.trigger_mode == "scheduled"


@pytest.mark.asyncio
async def test_ingest_csv_file_skips_blank_label_rows_with_error_log(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    file_path = tmp_path / "blank_label.csv"
    file_path.write_text(
        "text,label,source,language\nBonjour,,csv_blank_label,fr\n",
        encoding="utf-8",
    )

    caplog.set_level(logging.WARNING)

    async with session_factory() as session:
        result = await ingest_csv_file(
            file_path,
            session,
            SourceSystemQueries(),
            IngestionRunQueries(),
        )
        source_systems = list((await session.scalars(select(DataSourceSystem))).all())
        ingestion_runs = list((await session.scalars(select(DataIngestionRun))).all())
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.inserted_count == 0
    assert result.status == "skipped_invalid_rows"
    assert not source_systems
    assert not ingestion_runs
    assert not raw_records
    assert "label values are blank for row(s): 1" in caplog.text


@pytest.mark.asyncio
async def test_an_unreadable_file_returns_read_error_rather_than_raising(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """One corrupt file must not abort the batch."""
    file_path = tmp_path / "corrupt.csv"
    # A lone surrogate cannot be decoded as UTF-8.
    file_path.write_bytes(b"text,label\n\xed\xa0\x80broken,spam\n")

    async with session_factory() as session:
        result = await ingest_csv_file(
            file_path, session, SourceSystemQueries(), IngestionRunQueries()
        )
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.status == "read_error"
    assert result.inserted_count == 0
    assert not raw_records, "a file that could not be read must insert nothing"


@pytest.mark.asyncio
async def test_the_same_file_twice_is_ingested_once(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """Content-hash dedup is what makes the daily cron idempotent."""
    file_path = tmp_path / "spam_1.csv"
    file_path.write_text(
        "text,label\nBonjour ceci est un message de test,spam\n", encoding="utf-8"
    )

    async with session_factory() as session:
        first = await ingest_csv_file(
            file_path, session, SourceSystemQueries(), IngestionRunQueries()
        )
        await session.commit()

    async with session_factory() as session:
        second = await ingest_csv_file(
            file_path, session, SourceSystemQueries(), IngestionRunQueries()
        )
        await session.commit()
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert first.inserted_count == 1
    assert second.status == "skipped_unchanged"
    assert second.inserted_count == 0
    assert len(raw_records) == 1, "the second pass must not duplicate the record"


@pytest.mark.asyncio
async def test_a_dropzone_file_registers_its_governance(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """A source created by ingestion must not arrive without a legal basis."""
    file_path = tmp_path / "spam_2.csv"
    file_path.write_text(
        "text,label\nMessage de test pour la gouvernance,spam\n", encoding="utf-8"
    )

    async with session_factory() as session:
        await ingest_csv_file(
            file_path, session, SourceSystemQueries(), IngestionRunQueries()
        )
        await session.commit()
        source = (await session.scalars(select(DataSourceSystem))).one()

    assert source.legal_basis == "legitimate_interest_security"
    assert source.contains_personal_data is True
    assert source.retention_days == 365


@pytest.mark.asyncio
async def test_empty_bytes_are_reported_as_empty_not_ingested(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The R2 lane downloads bytes, so a zero-row object must be named as such."""
    from data_platform.base_ingest.file.parsers.csv_ingestion import ingest_csv_bytes

    async with session_factory() as session:
        result = await ingest_csv_bytes(
            b"text,label\n",
            "empty_spam_1.csv",
            "r2://raw/empty_spam_1.csv",
            "s3://bucket/empty_spam_1.csv",
            session,
            SourceSystemQueries(),
            IngestionRunQueries(),
        )
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.status == "empty"
    assert result.inserted_count == 0
    assert not raw_records


@pytest.mark.asyncio
async def test_bytes_from_r2_are_ingested_with_their_governance(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The R2 lane must register governance the same way the file lane does."""
    from data_platform.base_ingest.file.parsers.csv_ingestion import ingest_csv_bytes

    payload = b"text,label\nBonjour ceci est un message de test R2,spam\n"

    async with session_factory() as session:
        result = await ingest_csv_bytes(
            payload,
            "spam_9.csv",
            "r2://raw/spam_9.csv",
            "s3://bucket/spam_9.csv",
            session,
            SourceSystemQueries(),
            IngestionRunQueries(),
        )
        await session.commit()
        source = (await session.scalars(select(DataSourceSystem))).one()

    assert result.inserted_count == 1
    assert source.legal_basis == "legitimate_interest_security"
    assert source.contains_personal_data is True
