"""Seed the current_frozen provenance into data_dataset + data_dataset_item.

Reads data/final/provenance/current_frozen/sicurre_{train,val,test}.csv,
matches each row to data_normalized_message by sha256(text), and inserts:
  - 1 data_dataset row (version_tag from metadata.json)
  - N data_dataset_item rows (one per matched normalized message)

Usage:
    uv run python scripts/data_platform/seed_frozen_dataset.py
    uv run python scripts/data_platform/seed_frozen_dataset.py --skip-if-exists
    uv run python scripts/data_platform/seed_frozen_dataset.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

FROZEN_DIR = ROOT_DIR / "data" / "final" / "provenance" / "current_frozen"
SPLITS = ("train", "val", "test")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_frozen_rows(frozen_dir: Path) -> list[tuple[str, str, str]]:
    """Return list of (sha256, split_name, label) tuples from all split CSVs."""
    rows: list[tuple[str, str, str]] = []
    for split in SPLITS:
        csv_path = frozen_dir / f"sicurre_{split}.csv"
        if not csv_path.exists():
            logger.warning("Frozen CSV not found: %s — skipping split", csv_path)
            continue
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                text_val = row.get("text", "")
                label = row.get("label", "")
                if text_val:
                    rows.append((_sha256_hex(text_val), split, label))
    return rows


async def seed(
    *,
    db_url: str,
    frozen_dir: Path,
    skip_if_exists: bool,
    dry_run: bool,
) -> None:
    metadata_path = frozen_dir / "metadata.json"
    if not metadata_path.exists():
        logger.error("metadata.json not found at %s", metadata_path)
        raise SystemExit(1)

    with metadata_path.open(encoding="utf-8") as fh:
        meta = json.load(fh)

    version_tag: str = meta["version_tag"]
    expected_item_count: int = meta["item_count"]

    logger.info(
        "Frozen dataset: version_tag=%s  expected_items=%d",
        version_tag,
        expected_item_count,
    )

    # Load all frozen rows (sha256, split, label)
    frozen_rows = _load_frozen_rows(frozen_dir)
    logger.info("Loaded %d rows from frozen CSVs", len(frozen_rows))

    if not frozen_rows:
        logger.error("No rows loaded from frozen CSVs — aborting")
        raise SystemExit(1)

    # Build sha256 → (split, label) lookup
    sha_to_meta: dict[str, tuple[str, str]] = {
        sha: (split, label) for sha, split, label in frozen_rows
    }

    engine = create_async_engine(db_url, echo=False)
    async with async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )() as session:
        # Check if version already exists
        existing = await session.scalar(
            text("SELECT id FROM data_dataset WHERE version_tag = :vt").bindparams(
                vt=version_tag
            )
        )
        if existing:
            if skip_if_exists:
                logger.info(
                    "Dataset version_tag=%s already exists (id=%s) — skipping",
                    version_tag,
                    existing,
                )
                return
            logger.error(
                "Dataset version_tag=%s already exists. Use --skip-if-exists to skip.",
                version_tag,
            )
            raise SystemExit(1)

        # Query normalized messages whose sha256 is in our frozen set
        all_sha256s = list(sha_to_meta.keys())
        logger.info("Querying DB for %d sha256 hashes...", len(all_sha256s))

        # Batch query in chunks to avoid SQLite variable limit (999)
        chunk_size = 900
        matched: dict[str, uuid.UUID] = {}  # sha256 → normalized_message_id

        for i in range(0, len(all_sha256s), chunk_size):
            chunk = all_sha256s[i : i + chunk_size]
            placeholders = ", ".join(f":s{j}" for j in range(len(chunk)))
            params = {f"s{j}": sha for j, sha in enumerate(chunk)}
            stmt = text(
                f"SELECT id, text_sha256 FROM data_normalized_message "
                f"WHERE text_sha256 IN ({placeholders})"
            ).bindparams(**params)
            result = await session.execute(stmt)
            for row in result.fetchall():
                matched[row.text_sha256] = row.id

        match_count = len(matched)
        miss_count = len(all_sha256s) - match_count
        match_pct = 100 * match_count / len(all_sha256s) if all_sha256s else 0

        logger.info(
            "Match result: %d/%d matched (%.1f%%), %d unmatched",
            match_count,
            len(all_sha256s),
            match_pct,
            miss_count,
        )

        if match_count == 0:
            logger.error(
                "Zero matches found — DB may not have annotations yet. Run normalize + annotate first."
            )
            raise SystemExit(1)

        if dry_run:
            logger.info(
                "[dry-run] Would insert 1 data_dataset + %d data_dataset_item rows",
                match_count,
            )
            return

        # Insert data_dataset
        now = datetime.now(timezone.utc)
        dataset_id = uuid.uuid4()

        await session.execute(
            text(
                "INSERT INTO data_dataset "
                "(id, name, version_tag, target_usage, status, frozen_at, item_count, created_at) "
                "VALUES (:id, :name, :vt, :usage, :status, :frozen_at, :item_count, :created_at)"
            ).bindparams(
                id=dataset_id,
                name="sicurre_training",
                vt=version_tag,
                usage="training",
                status="frozen",
                frozen_at=now,
                item_count=match_count,
                created_at=now,
            )
        )
        logger.info("Inserted data_dataset (id=%s)", dataset_id)

        # Insert data_dataset_item rows in batches
        item_rows = []
        for row_order, (sha, split_name, _label) in enumerate(frozen_rows):
            nm_id = matched.get(sha)
            if nm_id is None:
                continue
            item_rows.append(
                {
                    "id": uuid.uuid4(),
                    "dataset_id": dataset_id,
                    "normalized_message_id": nm_id,
                    "split_name": split_name,
                    "sample_weight": 1.0,
                    "row_order": row_order,
                    "created_at": now,
                }
            )

        insert_batch_size = 500
        stmt = text(
            "INSERT INTO data_dataset_item "
            "(id, dataset_id, normalized_message_id, split_name, sample_weight, row_order, created_at) "
            "VALUES (:id, :dataset_id, :normalized_message_id, :split_name, :sample_weight, :row_order, :created_at)"
        )
        for i in range(0, len(item_rows), insert_batch_size):
            batch = item_rows[i : i + insert_batch_size]
            await session.execute(stmt, batch)
            await session.commit()
            logger.info(
                "Inserted dataset items batch %d/%d",
                min(i + insert_batch_size, len(item_rows)),
                len(item_rows),
            )

    await engine.dispose()

    logger.info(
        "Done. Seeded dataset version_tag=%s with %d items (%d unmatched from frozen CSV).",
        version_tag,
        match_count,
        miss_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed frozen dataset into data_dataset + data_dataset_item."
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLAlchemy async DB URL. Defaults to SICURRE_DATA_PLATFORM_DATABASE_URL.",
    )
    parser.add_argument(
        "--frozen-dir",
        type=Path,
        default=FROZEN_DIR,
        help="Path to current_frozen/ provenance directory.",
    )
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        default=False,
        help="Exit cleanly if version_tag already exists in DB.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be inserted without writing to DB.",
    )
    args = parser.parse_args()

    db_url = args.db_url
    if db_url is None:
        settings = get_settings()
        db_url = settings.data_platform_database_url

    asyncio.run(
        seed(
            db_url=db_url,
            frozen_dir=args.frozen_dir,
            skip_if_exists=args.skip_if_exists,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
