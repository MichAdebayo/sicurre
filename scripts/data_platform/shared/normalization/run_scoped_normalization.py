from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from db.models import (  # noqa: E402
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
    IngestionStatus,
)
from data_platform.services.shared.normalization_pipeline import (  # noqa: E402
    NormalizationPipeline,
)


async def _load_candidates(
    session: AsyncSession,
    ingestion_run_ids: tuple[UUID, ...],
) -> list[tuple[DataRawRecord, str]]:
    result = await session.execute(
        select(DataRawRecord, DataSourceSystem.name)
        .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
        .join(DataSourceSystem, DataRawRecord.source_system_id == DataSourceSystem.id)
        .outerjoin(
            DataNormalizedMessage,
            DataNormalizedMessage.raw_record_id == DataRawRecord.id,
        )
        .where(DataRawObject.ingestion_run_id.in_(ingestion_run_ids))
        .where(DataNormalizedMessage.id.is_(None))
        .where(DataRawRecord.detected_language == "fr")
        .where(DataRawRecord.is_usable.is_(True))
        .order_by(DataRawRecord.created_at.asc(), DataRawRecord.id.asc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def _run(
    ingestion_run_ids: tuple[UUID, ...],
    *,
    write: bool,
) -> dict[str, object]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    try:
        async with session_factory() as session:
            pipeline = NormalizationPipeline(session)
            candidates = await _load_candidates(session, ingestion_run_ids)

            source_totals: Counter[str] = Counter(
                source_name for _, source_name in candidates
            )
            selected_records: list[tuple[DataRawRecord, str]] = []
            skipped_by_policy: Counter[str] = Counter()
            for raw_record, source_name in candidates:
                policy = pipeline.get_source_policy(source_name)
                if policy is None or not policy.normalize_messages:
                    skipped_by_policy.update([source_name])
                    continue
                selected_records.append((raw_record, source_name))

            preview: dict[str, object] = {
                "mode": "write" if write else "preview",
                "ingestion_run_ids": [str(run_id) for run_id in ingestion_run_ids],
                "candidate_count": len(candidates),
                "source_totals": dict(sorted(source_totals.items())),
                "selected_count": len(selected_records),
                "skipped_by_policy": dict(sorted(skipped_by_policy.items())),
            }
            if not selected_records:
                return {
                    **preview,
                    "normalized": 0,
                    "skipped_not_accepted": 0,
                    "skipped_duplicate": 0,
                    "skipped_error": 0,
                    "processing_run_id": None,
                }

            existing_hashes = set(
                (await session.scalars(select(DataNormalizedMessage.text_sha256))).all()
            )

            normalized = 0
            skipped_not_accepted = 0
            skipped_duplicate = 0
            skipped_error = 0
            normalized_by_source: Counter[str] = Counter()
            rejected_by_source: Counter[str] = Counter()
            duplicate_by_source: Counter[str] = Counter()
            processing_run: DataProcessingRun | None = None

            if write:
                processing_run = DataProcessingRun(
                    pipeline_version=NormalizationPipeline.PIPELINE_VERSION,
                    started_at=pipeline._utc_now(),
                    status=IngestionStatus.RUNNING.value,
                )
                session.add(processing_run)
                await session.flush()

            for raw_record, source_name in selected_records:
                try:
                    payload = pipeline.extract_payload(
                        source_name,
                        json.loads(raw_record.raw_content),
                    )
                except Exception:
                    skipped_error += 1
                    rejected_by_source.update([source_name])
                    continue

                if (
                    payload.route_outcome != "accepted"
                    or not payload.text
                    or payload.label is None
                ):
                    skipped_not_accepted += 1
                    rejected_by_source.update([source_name])
                    continue

                text_hash = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
                if text_hash in existing_hashes:
                    skipped_duplicate += 1
                    duplicate_by_source.update([source_name])
                    continue

                normalized += 1
                normalized_by_source.update([source_name])
                existing_hashes.add(text_hash)

                if write and processing_run is not None:
                    session.add(
                        DataNormalizedMessage(
                            raw_record_id=raw_record.id,
                            processing_run_id=processing_run.id,
                            normalized_text=payload.text,
                            text_sha256=text_hash,
                            language="fr",
                            current_label=payload.label.value,
                            contains_pii=payload.contains_pii,
                            redaction_status=payload.redaction_status.value,
                            text_length=len(payload.text),
                            normalized_at=pipeline._utc_now(),
                        )
                    )

            if write and processing_run is not None:
                processing_run.status = IngestionStatus.COMPLETED.value
                processing_run.normalized_count = normalized
                processing_run.rejected_count = (
                    skipped_not_accepted + skipped_duplicate + skipped_error
                )
                processing_run.finished_at = pipeline._utc_now()
                await session.commit()

            return {
                **preview,
                "normalized": normalized,
                "skipped_not_accepted": skipped_not_accepted,
                "skipped_duplicate": skipped_duplicate,
                "skipped_error": skipped_error,
                "normalized_by_source": dict(sorted(normalized_by_source.items())),
                "rejected_by_source": dict(sorted(rejected_by_source.items())),
                "duplicate_by_source": dict(sorted(duplicate_by_source.items())),
                "processing_run_id": str(processing_run.id) if processing_run else None,
            }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize only the raw records produced by specific ingestion runs."
    )
    parser.add_argument(
        "--ingestion-run-id",
        action="append",
        required=True,
        dest="ingestion_run_ids",
        help="Repeat for each ingestion run ID to include.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist new normalized messages. Without this flag, the script only previews.",
    )
    args = parser.parse_args()

    result = asyncio.run(
        _run(
            tuple(UUID(value) for value in args.ingestion_run_ids),
            write=args.write,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()