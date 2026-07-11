from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from data_platform.extractors.legacy_db import (
    LegacyDbConnector,
    LegacyDbIngestionService,
)
from db.models import DataRawObject, DataSourceSystem, ObjectType, SourceType


def _prepare_external_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL
            );

            CREATE TABLE threat_log (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                subject TEXT,
                body_preview TEXT,
                verdict TEXT,
                confidence REAL,
                signals TEXT,
                archetype TEXT,
                source_dataset TEXT,
                received_at TEXT,
                created_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?)",
            ("user-1", "owner@example.fr"),
        )
        conn.execute(
            """
            INSERT INTO threat_log (
                id, user_id, message_id, subject, body_preview, verdict,
                confidence, signals, archetype, source_dataset, received_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "threat-1",
                "user-1",
                "msg-1",
                "Sujet",
                "Corps",
                "phishing",
                0.98,
                "[]",
                "banking",
                "synthetic_phishing_medium",
                "2026-04-17T08:00:00+00:00",
                "2026-04-17T08:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_legacy_db_connector_uses_configured_sqlite_path(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test_external_threats.db"
    _prepare_external_db(db_path)

    connector = LegacyDbConnector(db_url=f"sqlite+aiosqlite:///{db_path}")

    rows = await connector.fetch_threats()

    assert len(rows) == 1
    assert rows[0]["message_id"] == "msg-1"
    assert rows[0]["source_dataset"] == "synthetic_phishing_medium"


@pytest.mark.asyncio
async def test_legacy_db_connector_error_mentions_configured_path(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing_external_threats.db"
    connector = LegacyDbConnector(db_url=f"sqlite+aiosqlite:///{missing_path}")

    with pytest.raises(FileNotFoundError) as excinfo:
        await connector.fetch_threats()

    assert str(missing_path) in str(excinfo.value)


def test_legacy_db_ingestion_preserves_multiclass_verdicts() -> None:
    service = LegacyDbIngestionService()
    raw_object = DataRawObject(
        id=uuid.uuid4(),
        ingestion_run_id=uuid.uuid4(),
        object_type=ObjectType.SQL_EXPORT.value,
        content_hash="test-hash",
        source_metadata={},
        collected_at=datetime.now(timezone.utc),
    )
    spam_source_name = "database/faker/synthetic_spam_medium"
    phishing_source_name = "database/faker/synthetic_phishing_medium"
    source_systems_by_name = {
        spam_source_name: DataSourceSystem(
            id=uuid.uuid4(),
            name=spam_source_name,
            source_type=SourceType.SQL.value,
        ),
        phishing_source_name: DataSourceSystem(
            id=uuid.uuid4(),
            name=phishing_source_name,
            source_type=SourceType.SQL.value,
        ),
    }

    raw_records = service._build_raw_records(
        raw_object=raw_object,
        entries=[
            {
                "message_id": "msg-spam",
                "subject": "Offre",
                "body_preview": "Promotion limitée",
                "verdict": "spam",
                "source_dataset": "synthetic_spam_medium",
            },
            {
                "message_id": "msg-phishing",
                "subject": "Compte",
                "body_preview": "Veuillez confirmer votre compte",
                "verdict": "phishing",
                "source_dataset": "synthetic_phishing_medium",
            },
        ],
        source_systems_by_name=source_systems_by_name,
    )
    raw_contents = {
        record.record_key: json.loads(record.raw_content) for record in raw_records
    }

    assert raw_contents["msg-spam"]["label"] == "spam"
    assert raw_contents["msg-phishing"]["label"] == "phishing"
