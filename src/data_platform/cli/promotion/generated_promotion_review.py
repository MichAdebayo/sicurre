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
from data_platform.services.shared.review_persistence import (  # noqa: E402
    ReviewPersistenceService,
)


def _resolve_selected_draft_ids(
    payload: dict[str, Any], cli_draft_ids: list[str] | None
) -> list[str]:
    selected_draft_ids = list(cli_draft_ids or payload.get("selected_draft_ids") or [])
    return list(
        dict.fromkeys(str(draft_id) for draft_id in selected_draft_ids if draft_id)
    )


def _resolve_samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("promoted_samples") or payload.get("samples") or [])


def _build_preview(
    *,
    bundle_json: Path,
    payload: dict[str, Any],
    selected_draft_ids: list[str],
    selected_samples: list[dict[str, Any]],
    pipeline_version: str,
    report_uri: str | None,
    source_system_name: str | None,
) -> dict[str, Any]:
    run_payload = dict(payload.get("run") or {})
    return {
        "mode": "preview",
        "bundle_json": str(bundle_json),
        "generator_name": run_payload.get("generator_name"),
        "source_name": run_payload.get("source_name"),
        "pipeline_version": pipeline_version,
        "report_uri": report_uri or str(bundle_json),
        "source_system_name": source_system_name,
        "selected_draft_ids": selected_draft_ids,
        "selected_sample_count": len(selected_samples),
        "selected_samples": [
            {
                "draft_id": sample.get("draft_id"),
                "variant_index": sample.get("variant_index"),
                "review_state": sample.get("review_state"),
                "target_label": sample.get("target_label"),
                "text_sha256": sample.get("text_sha256"),
            }
            for sample in selected_samples
        ],
    }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Persist explicit selected generated drafts into synthetic raw lineage, "
            "data_normalized_message, and provisional data_annotation rows."
        )
    )
    parser.add_argument("--bundle-json", type=Path, required=True)
    parser.add_argument(
        "--draft-id",
        action="append",
        default=None,
        help="Explicit draft_id to promote. Repeat for multiple selections.",
    )
    parser.add_argument(
        "--pipeline-version",
        type=str,
        default="generated_reviewed_promotion_v1",
    )
    parser.add_argument("--report-uri", type=str, default=None)
    parser.add_argument("--source-system-name", type=str, default=None)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the selected generated drafts. Without this flag, the script only prints a preview.",
    )
    args = parser.parse_args()

    payload = json.loads(args.bundle_json.read_text(encoding="utf-8"))
    samples = _resolve_samples(payload)
    selected_draft_ids = _resolve_selected_draft_ids(payload, args.draft_id)
    if not selected_draft_ids:
        raise SystemExit(
            "Provide at least one --draft-id or include selected_draft_ids in the bundle JSON."
        )

    selected_samples = [
        sample
        for sample in samples
        if str(sample.get("draft_id") or "") in selected_draft_ids
    ]
    matched_draft_ids = {
        str(sample.get("draft_id") or "") for sample in selected_samples
    }
    missing_draft_ids = [
        draft_id for draft_id in selected_draft_ids if draft_id not in matched_draft_ids
    ]
    if missing_draft_ids:
        raise SystemExit(
            f"Selected draft ids were not found in the bundle: {', '.join(missing_draft_ids)}"
        )

    invalid_draft_ids = sorted(
        {
            str(sample.get("draft_id") or "")
            for sample in selected_samples
            if str(sample.get("review_state") or "") != "usable"
        }
    )
    if invalid_draft_ids:
        raise SystemExit(
            "Only usable drafts can be promoted. Invalid selections: "
            f"{', '.join(invalid_draft_ids)}"
        )

    preview = _build_preview(
        bundle_json=args.bundle_json,
        payload=payload,
        selected_draft_ids=selected_draft_ids,
        selected_samples=selected_samples,
        pipeline_version=args.pipeline_version,
        report_uri=args.report_uri,
        source_system_name=args.source_system_name,
    )
    if not args.write:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    write_payload = {
        "run": payload.get("run"),
        "promoted_samples": samples,
        "selected_draft_ids": selected_draft_ids,
    }
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await ReviewPersistenceService.persist_generated_promotion_review(
                session,
                write_payload,
                pipeline_version=args.pipeline_version,
                report_uri=args.report_uri or str(args.bundle_json),
                source_system_name=args.source_system_name,
            )
    finally:
        await engine.dispose()

    print(
        json.dumps({**preview, **result, "mode": "write"}, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    asyncio.run(main())
