from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sicurre_api.core.database import Base
from sicurre_api.domains.data_platform.models import (
    DataIngestionRun,
    DataRawObject,
    DataRawRecord,
)
from sicurre_api.domains.data_platform.services.certfr import (
    CertFRFeedClient,
    CertFRIngestionService,
)
from sicurre_api.domains.data_platform.services.snapshot_storage import (
    LocalSnapshotStore,
    SnapshotWriteResult,
)


class RecordingSnapshotStore:
    def __init__(self) -> None:
        self.object_key: str | None = None

    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return f"raw-snapshots/{source_prefix}/{filename}"

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult:
        self.object_key = object_key
        return SnapshotWriteResult(
            storage_uri=f"r2://sicurre-raw/{object_key}",
            content_hash="hash",
            size_bytes=len(payload),
            local_path=None,
        )


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


@pytest.mark.asyncio
async def test_certfr_ingestion_persists_lineage(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    entries = {
        "actualite": [
            {
                "title": "Bulletin d'actualité CERTFR-2025-ACT-030 (21 juillet 2025)",
                "link": "https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-030/",
                "guid": "https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-030/",
                "published": "Mon, 21 Jul 2025 00:00:00 +0000",
                "summary": "Résumé actualité.",
            }
        ],
        "alerte": [
            {
                "title": "Vulnérabilité dans les produits Ivanti",
                "link": "https://www.cert.ssi.gouv.fr/alerte/CERTFR-2025-ALE-001/",
                "guid": "https://www.cert.ssi.gouv.fr/alerte/CERTFR-2025-ALE-001/",
                "published": "Wed, 07 May 2025 00:00:00 +0000",
                "summary": "Résumé alerte.",
            }
        ],
        "cti": [
            {
                "title": "🇬🇧 Targeting and compromise of french entities using the APT28 intrusion set (29 avril 2025)",
                "link": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-007/",
                "guid": "https://www.cert.ssi.gouv.fr/cti/CERTFR-2025-CTI-007/",
                "published": "Tue, 29 Apr 2025 00:00:00 +0000",
                "summary": "Version française: 🇫🇷 ...",
            }
        ],
    }

    async def fetch_entries() -> dict[str, list[dict[str, object]]]:
        return entries

    local_store = LocalSnapshotStore(root_dir=tmp_path, repo_root=tmp_path)

    service = CertFRIngestionService(
        fetch_entries=fetch_entries,
        snapshot_dir=tmp_path,
        snapshot_store=local_store,
    )

    async with session_factory() as session:
        result = await service.run(
            session,
            trigger_mode="scheduled",
            started_at=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc),
        )

        ingestion_run = await session.scalar(select(DataIngestionRun))
        raw_object = await session.scalar(select(DataRawObject))
        raw_records = list((await session.scalars(select(DataRawRecord))).all())

    assert result.raw_object_count == 1
    assert result.raw_record_count == 3
    assert result.snapshot_path is not None
    assert result.snapshot_path.exists()
    assert result.snapshot_path.parent == tmp_path / "cert-fr"
    assert result.snapshot_storage_uri.endswith(".json")
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"
    assert ingestion_run.trigger_mode == "scheduled"
    assert raw_object is not None
    assert raw_object.storage_uri == result.snapshot_storage_uri
    assert raw_object.source_metadata["feed_counts"] == {
        "actualite": 1,
        "alerte": 1,
        "cti": 1,
    }
    assert raw_object.source_metadata["source_feed_format"] == "rss"
    assert len(raw_records) == 3
    assert {record.record_key for record in raw_records} == {
        "CERTFR-2025-ACT-030",
        "CERTFR-2025-ALE-001",
        "CERTFR-2025-CTI-007",
    }
    assert {record.detected_language for record in raw_records} == {"fr", "en"}


def test_certfr_feed_client_parses_rss_payload() -> None:
    payload = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>CERT-FR</title>
    <item>
      <title>Bulletin d'actualite CERTFR-2025-ACT-030</title>
      <link>https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-030/</link>
      <description>Resume actualite</description>
      <guid isPermaLink=\"true\">https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-030/</guid>
      <pubDate>Mon, 21 Jul 2025 00:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

    entries = CertFRFeedClient._parse_feed_payload("actualite", payload)

    assert entries == [
        {
            "title": "Bulletin d'actualite CERTFR-2025-ACT-030",
            "link": "https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-030/",
            "guid": "https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-030/",
            "summary": "Resume actualite",
            "published": "Mon, 21 Jul 2025 00:00:00 +0000",
            "updated": None,
            "reference": "CERTFR-2025-ACT-030",
            "categories": [],
        }
    ]


@pytest.mark.asyncio
async def test_certfr_ingestion_uses_source_prefix_for_r2_keys(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    entries = {
        "actualite": [
            {
                "title": "Bulletin d'actualité CERTFR-2025-ACT-030",
                "link": "https://www.cert.ssi.gouv.fr/actualite/CERTFR-2025-ACT-030/",
            }
        ],
        "alerte": [],
        "avis": [],
        "cti": [],
    }
    recording_store = RecordingSnapshotStore()

    async def fetch_entries() -> dict[str, list[dict[str, str]]]:
        return entries

    service = CertFRIngestionService(
        fetch_entries=fetch_entries,
        snapshot_store=recording_store,
    )

    async with session_factory() as session:
        result = await service.run(session, trigger_mode="scheduled")

    assert recording_store.object_key is not None
    assert recording_store.object_key.startswith("raw-snapshots/cert-fr/")
    assert result.snapshot_path is None
    assert result.snapshot_storage_uri.startswith(
        "r2://sicurre-raw/raw-snapshots/cert-fr/"
    )


@pytest.mark.asyncio
async def test_certfr_ingestion_marks_failed_runs(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    async def fetch_entries() -> dict[str, list[dict[str, str]]]:
        raise RuntimeError("feed unavailable")

    local_store = LocalSnapshotStore(root_dir=tmp_path, repo_root=tmp_path)

    service = CertFRIngestionService(
        fetch_entries=fetch_entries,
        snapshot_dir=tmp_path,
        snapshot_store=local_store,
    )

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="feed unavailable"):
            await service.run(session, trigger_mode="scheduled")

        ingestion_run = await session.scalar(select(DataIngestionRun))

    assert ingestion_run is not None
    assert ingestion_run.status == "failed"
    assert ingestion_run.raw_object_count == 0
    assert ingestion_run.raw_record_count == 0
