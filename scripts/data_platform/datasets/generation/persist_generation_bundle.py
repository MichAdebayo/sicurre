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

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from core.config import get_settings
from data_platform.services.review_persistence import ReviewPersistenceService


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persist a certified generation bundle into data_generation_run and data_generation_sample."
    )
    parser.add_argument("--bundle-json", type=Path, required=True)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the bundle. Without this flag, the script only prints a preview.",
    )
    args = parser.parse_args()

    payload = json.loads(args.bundle_json.read_text(encoding="utf-8"))
    if not args.write:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "bundle_json": str(args.bundle_json),
                    "run": payload.get("run"),
                    "sample_count": len(payload.get("samples") or []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await ReviewPersistenceService.persist_generation_bundle(
                session,
                payload,
            )
    finally:
        await engine.dispose()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
