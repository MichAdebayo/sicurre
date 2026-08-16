"""Publish a reviewed evaluation set and register its immutable manifest."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from core.config import ROOT_DIR
from core.database import AsyncSessionFactory
from data_platform.api.schemas.mlops import EvaluationSetRegistration
from data_platform.services.evaluation_set_asset import (
    build_evaluation_asset,
    load_evaluation_records,
)
from data_platform.services.model_provenance import register_evaluation_set
from data_platform.services.shared.snapshot_storage import build_evaluation_set_store


def parse_args() -> argparse.Namespace:
    """Parse the explicit human-reviewed publication contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--version-tag", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--backend", choices=("r2", "prod"), default="r2")
    return parser.parse_args()


async def publish(args: argparse.Namespace) -> EvaluationSetRegistration:
    """Validate, store, and register one immutable approved version."""
    records = load_evaluation_records(args.input.read_bytes())
    asset = build_evaluation_asset(records)
    store = build_evaluation_set_store(
        local_root_dir=ROOT_DIR / "data" / "local" / "evaluation_sets",
        repo_root=ROOT_DIR,
        backend=args.backend,
    )
    object_key = store.build_object_key(
        source_prefix=f"evaluation_sets/{args.version_tag}",
        filename="golden.jsonl",
    )
    result = await store.write_snapshot(
        object_key=object_key,
        payload=asset.jsonl,
        content_type="application/x-ndjson; charset=utf-8",
    )
    registration = EvaluationSetRegistration.model_validate(
        {
            "name": "sicurre-provisional-golden-set",
            "version_tag": args.version_tag,
            "schema_version": "1",
            "provenance": "synthetic_provisional",
            "status": "approved",
            "object_uri": result.storage_uri,
            "content_checksum": asset.checksum,
            "item_count": asset.item_count,
            "label_counts": asset.label_counts,
            "language_counts": asset.language_counts,
            "reviewed_by": args.reviewed_by,
            "reviewed_at": args.reviewed_at,
        }
    )
    async with AsyncSessionFactory() as session:
        await register_evaluation_set(session, registration)
    return registration


def main() -> None:
    """Run the reviewed publication workflow."""
    registration = asyncio.run(publish(parse_args()))
    print(registration.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
