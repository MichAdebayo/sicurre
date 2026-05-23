from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from data_platform.services.shared.annotation_backfill import (  # noqa: E402
    AnnotationBackfillService,
)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill data_annotation rows for normalized messages that do not yet have "
            "annotations."
        )
    )
    parser.add_argument(
        "--source-name",
        action="append",
        default=None,
        help="Optional source system name to limit the backfill. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist missing annotations. Without this flag, the runner only prints a preview.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await AnnotationBackfillService.backfill_missing_annotations(
                session,
                source_names=tuple(args.source_name) if args.source_name else None,
                dry_run=not args.write,
            )
    finally:
        await engine.dispose()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
