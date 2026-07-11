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
from data_platform.services.shared.review_persistence import ReviewPersistenceService


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Persist a certified Common Crawl acceptance review into "
            "data_processing_run, data_normalized_message, and data_annotation."
        )
    )
    parser.add_argument("--review-json", type=Path, required=True)
    parser.add_argument(
        "--pipeline-version",
        type=str,
        default="common_crawl_reviewed_promotion_v1",
    )
    parser.add_argument("--report-uri", type=str, default=None)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the accepted curated pilot. Without this flag, the script only prints a preview.",
    )
    args = parser.parse_args()

    payload = json.loads(args.review_json.read_text(encoding="utf-8"))
    preview = {
        "mode": "preview",
        "review_json": str(args.review_json),
        "accepted_candidate_count": payload.get("accepted_candidate_count"),
        "rejected_candidate_count": payload.get("rejected_candidate_count"),
        "proposed_normalized_message_count": len(
            payload.get("proposed_normalized_messages") or []
        ),
        "proposed_annotation_count": len(payload.get("proposed_annotations") or []),
    }
    if not args.write:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = (
                await ReviewPersistenceService.persist_common_crawl_acceptance_review(
                    session,
                    payload,
                    pipeline_version=args.pipeline_version,
                    report_uri=args.report_uri or str(args.review_json),
                )
            )
    finally:
        await engine.dispose()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
