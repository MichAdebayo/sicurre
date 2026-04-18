from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from db.models import DataIngestionRun, DataRawRecord, DataSourceSystem
from db.queries import IngestionRunQueries, SourceSystemQueries
from data_platform.cli.ingest.file.csv_ingestion import ingest_csv_file


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
    assert "missing optional columns: language" in caplog.text


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
