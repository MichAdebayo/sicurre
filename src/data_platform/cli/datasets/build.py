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
from core.trace_logger import SemanticTraceLogger  # noqa: E402
from db.models import DatasetStatus  # noqa: E402
from db.queries import DatasetBuildEmptyError, DuplicateDatasetError  # noqa: E402
from db.services import DatasetService  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a DB-backed dataset version from annotated normalized messages and "
            "populate data_dataset_item with deterministic splits."
        )
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--version-tag", required=True)
    parser.add_argument("--target-usage", default="training")
    parser.add_argument(
        "--status",
        default=DatasetStatus.FROZEN.value,
        choices=[item.value for item in DatasetStatus],
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the dataset build. Without this flag, the runner only prints the requested configuration.",
    )
    args = parser.parse_args()
    trace = SemanticTraceLogger(
        parent_type="Dataset",
        child_target="Dataset Build",
        domain="data_platform",
    )
    trace.trace(
        stage="orchestration",
        status="start",
        message="Dataset build CLI starting",
        metrics={"write": int(args.write)},
    )

    preview = {
        "mode": "preview",
        "name": args.name,
        "version_tag": args.version_tag,
        "target_usage": args.target_usage,
        "status": args.status,
    }
    if not args.write:
        trace.trace(
            stage="dataset_freeze",
            status="success",
            message="Dataset build preview generated",
            metrics={"version_tag": args.version_tag},
        )
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    settings = get_settings()
    engine = create_async_engine(settings.data_platform_database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            try:
                result = await DatasetService().build(
                    session,
                    name=args.name,
                    version_tag=args.version_tag,
                    target_usage=args.target_usage,
                    status=args.status,
                )
            except DatasetBuildEmptyError:
                trace.trace(
                    stage="dataset_freeze",
                    status="failed",
                    message="Dataset build failed: no eligible annotated normalized messages found",
                )
                print(
                    json.dumps(
                        {
                            **preview,
                            "mode": "write",
                            "error": "No eligible annotated normalized messages found",
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                raise SystemExit(1)
            except DuplicateDatasetError:
                trace.trace(
                    stage="dataset_freeze",
                    status="failed",
                    message="Dataset build failed: dataset version already exists",
                )
                print(
                    json.dumps(
                        {
                            **preview,
                            "mode": "write",
                            "error": "Dataset version already exists",
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                raise SystemExit(1)
    finally:
        await engine.dispose()

    trace.trace(
        stage="dataset_freeze",
        status="success",
        message="Dataset build completed",
        metrics={"item_count": result.dataset.item_count},
    )

    print(
        json.dumps(
            {
                **preview,
                "mode": "write",
                "dataset_id": str(result.dataset.id),
                "item_count": result.dataset.item_count,
                "split_counts": result.split_counts,
                "frozen_at": (
                    result.dataset.frozen_at.isoformat()
                    if result.dataset.frozen_at is not None
                    else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
