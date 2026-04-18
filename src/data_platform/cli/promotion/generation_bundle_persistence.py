from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from db.models import AnnotationLabelSource  # noqa: E402
from data_platform.services.shared.review_persistence import (  # noqa: E402
    ReviewPersistenceService,
)


def _load_payload(bundle_json: Path) -> dict[str, Any]:
    return json.loads(bundle_json.read_text(encoding="utf-8"))


def _collect_samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("samples") or payload.get("promoted_samples") or [])


def _count_promotable_samples(payload: dict[str, Any]) -> int:
    return sum(
        1
        for sample in _collect_samples(payload)
        if str(sample.get("review_state") or "") == "usable"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Persist a generation bundle into data_generation_run/data_generation_sample "
            "and auto-promote the gated usable subset into curated storage."
        )
    )
    parser.add_argument("--bundle-json", type=Path, required=True)
    parser.add_argument(
        "--pipeline-version",
        type=str,
        default="generation_gated_promotion_v1",
    )
    parser.add_argument("--report-uri", type=str, default=None)
    parser.add_argument("--source-system-name", type=str, default=None)
    parser.add_argument(
        "--annotation-label-source",
        type=str,
        default=AnnotationLabelSource.GENERATION_GATED_PROMOTION.value,
        help=(
            "Annotation label_source to stamp on provisional annotations. "
            "Default: generation_gated_promotion."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the bundle and gated promotions. Without this flag, the script only prints a preview.",
    )
    args = parser.parse_args()

    payload = _load_payload(args.bundle_json)
    preview = {
        "mode": "preview",
        "bundle_json": str(args.bundle_json),
        "run": payload.get("run"),
        "sample_count": len(_collect_samples(payload)),
        "promotable_sample_count": _count_promotable_samples(payload),
        "annotation_label_source": args.annotation_label_source,
        "pipeline_version": args.pipeline_version,
        "report_uri": args.report_uri or str(args.bundle_json),
        "source_system_name": args.source_system_name,
    }
    if not args.write:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await ReviewPersistenceService.persist_generation_bundle_with_gated_promotion(
                session,
                payload,
                pipeline_version=args.pipeline_version,
                report_uri=args.report_uri or str(args.bundle_json),
                source_system_name=args.source_system_name,
                annotation_label_source=args.annotation_label_source,
            )
    finally:
        await engine.dispose()

    print(
        json.dumps({**preview, **result, "mode": "write"}, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    asyncio.run(main())
