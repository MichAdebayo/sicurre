from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

load_dotenv(ROOT_DIR / ".env")

from core.config import get_settings  # noqa: E402
from data_platform.services.common_crawl_promotion_review import (  # noqa: E402
    CommonCrawlPromotionReviewService,
)
from data_platform.services.review_persistence import ReviewPersistenceService  # noqa: E402
from data_platform.services.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build and optionally persist a Common Crawl reviewed export directly "
            "into curated storage without an intermediate acceptance-review JSON artifact."
        )
    )
    parser.add_argument("--reviewed-export-json", type=Path, required=True)
    parser.add_argument(
        "--pipeline-version",
        type=str,
        default="common_crawl_reviewed_promotion_v1",
    )
    parser.add_argument("--report-uri", type=str, default=None)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist accepted candidates into curated storage. Without this flag, only print a preview.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    export_payload = StructuredReviewArtifactService.read_json(args.reviewed_export_json)
    acceptance_preview = CommonCrawlPromotionReviewService.build_acceptance_review(
        export_payload
    )

    preview = {
        "mode": "preview",
        "reviewed_export_json": str(args.reviewed_export_json),
        "reviewed_candidate_count": acceptance_preview.get("reviewed_candidate_count"),
        "accepted_candidate_count": acceptance_preview.get("accepted_candidate_count"),
        "rejected_candidate_count": acceptance_preview.get("rejected_candidate_count"),
        "accepted_label_summary": acceptance_preview.get("accepted_label_summary"),
        "rejection_summary": acceptance_preview.get("rejection_summary"),
    }
    if not args.write:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await ReviewPersistenceService.persist_common_crawl_reviewed_export(
                session,
                export_payload,
                pipeline_version=args.pipeline_version,
                report_uri=args.report_uri or str(args.reviewed_export_json),
            )
    finally:
        await engine.dispose()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())