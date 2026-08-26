"""Replay the retained PhishTank export as local API-origin POC evidence."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from data_platform.extractors.phishtank import (
    PhishTankFetchedPayload,
    PhishTankIngestionService,
)
from data_platform.services.shared.snapshot_storage import LocalSnapshotStore
from db.models import DataRawRecord
from poc.config import ROOT_DIR, get_poc_settings

EXPORT_PATH = ROOT_DIR / "data" / "exports" / "phishtank_urls.json"


def load_export(path: Path = EXPORT_PATH) -> PhishTankFetchedPayload:
    """Load the retained local export without contacting PhishTank or R2."""
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    entries = [{"url": str(url)} for url in payload.get("urls", []) if str(url).strip()]
    return PhishTankFetchedPayload(
        entries=entries,
        snapshot_bytes=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
        source_format="json",
        source_url="https://data.phishtank.com/data/online-valid.csv",
    )


async def replay_api_evidence() -> int:
    """Persist idempotent API lineage in the local POC database."""
    settings = get_poc_settings()
    fetched = load_export()

    async def fetch_local() -> PhishTankFetchedPayload:
        return fetched

    snapshot_root = settings.snapshot_dir / "api"
    service = PhishTankIngestionService(
        fetch_entries=fetch_local,
        snapshot_store=LocalSnapshotStore(root_dir=snapshot_root, repo_root=ROOT_DIR),
        source_name="PhishTank API (rejeu local)",
    )
    engine = create_async_engine(settings.data_platform_database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await service.run(session, trigger_mode="poc_replay")
            await session.execute(
                update(DataRawRecord)
                .where(DataRawRecord.source_system_id == uuid.UUID(result.source_system_id))
                .values(
                    is_usable=False,
                    rejection_reason="ioc_reference_only_not_email_training_text",
                )
            )
            await session.commit()
            return result.raw_record_count
    finally:
        await engine.dispose()


def main() -> None:
    """Run the local replay and print concise evidence."""
    inserted = asyncio.run(replay_api_evidence())
    print(f"PhishTank API local replay complete: {inserted} new records.")


if __name__ == "__main__":
    main()
