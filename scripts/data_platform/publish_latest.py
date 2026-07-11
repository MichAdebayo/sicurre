from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings
from core.database import AsyncSessionFactory
from data_platform.services.dataset_publish import (
    DatasetPublishService,
    GitHubDispatchPublishError,
)
from data_platform.services.shared.kaggle_gateway import KaggleGateway, write_split_csv
from db.models.lineage import DataDataset, SplitName
from db.queries.records import DatasetQueries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish a frozen data-platform dataset to Kaggle."
    )
    parser.add_argument(
        "--version-tag",
        help="Frozen data_dataset.version_tag to publish. Defaults to latest frozen.",
    )
    parser.add_argument(
        "--skip-github-dispatch",
        action="store_true",
        help="Push the Kaggle version and update DB without dispatching ML training.",
    )
    return parser.parse_args()


async def _select_dataset(
    queries: DatasetQueries,
    session,
    *,
    version_tag: str | None,
) -> DataDataset:
    datasets, _ = await queries.list(session, limit=50, offset=0, status="frozen")
    if not datasets:
        raise RuntimeError("No frozen datasets found.")
    if version_tag is None:
        return datasets[0]
    for dataset in datasets:
        if dataset.version_tag == version_tag:
            return dataset
    available = ", ".join(dataset.version_tag for dataset in datasets)
    raise RuntimeError(
        f"Frozen dataset with version_tag={version_tag!r} not found. "
        f"Available frozen tags: {available}"
    )


async def _publish_kaggle_only(
    queries: DatasetQueries,
    session,
    dataset: DataDataset,
) -> int:
    settings = get_settings()
    if not settings.kaggle_username or not settings.kaggle_key:
        raise RuntimeError("Kaggle publish requires KAGGLE_USERNAME and KAGGLE_API_TOKEN")
    if not settings.kaggle_dataset_slug:
        raise RuntimeError("Kaggle publish requires KAGGLE_DATASET_SLUG")

    gateway = KaggleGateway(
        username=settings.kaggle_username,
        key=settings.kaggle_key,
    )
    with tempfile.TemporaryDirectory() as tmp:
        export_dir = Path(tmp)
        split_counts: dict[str, int] = {}
        for split in (item.value for item in SplitName):
            rows_raw = await queries.list_items_for_export(
                session,
                dataset.id,
                split_name=split,
            )
            split_counts[split] = len(rows_raw)
            if rows_raw:
                rows = [{"text": text, "label": label} for text, label in rows_raw]
                write_split_csv(rows, export_dir / f"{split}.csv")
        exported_files = sorted(item.name for item in export_dir.glob("*.csv"))
        print(f"Export split counts: {split_counts}")
        print(f"Exported files: {exported_files}")
        kaggle_version_id = await gateway.push_version(
            slug=settings.kaggle_dataset_slug,
            export_dir=export_dir,
            message=f"Dataset {dataset.version_tag} - replay publish smoke",
        )

    await queries.update_publish_result(
        session,
        dataset.id,
        kaggle_version_id=kaggle_version_id,
        published_at=datetime.now(timezone.utc),
    )
    return kaggle_version_id


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    queries = DatasetQueries()

    async with AsyncSessionFactory() as session:
        target_dataset = await _select_dataset(
            queries,
            session,
            version_tag=args.version_tag,
        )

        print("Publishing dataset:")
        print(f"- ID: {target_dataset.id}")
        print(f"- Tag: {target_dataset.version_tag}")
        print(f"- Count: {target_dataset.item_count}")
        print(f"- Skip GitHub dispatch: {args.skip_github_dispatch}")

        if args.skip_github_dispatch:
            version_id = await _publish_kaggle_only(queries, session, target_dataset)
            slug = settings.kaggle_dataset_slug
            print("\n============================================================")
            print("Kaggle publish successful.")
            print(f"Kaggle URL: https://www.kaggle.com/datasets/{slug}/versions/{version_id}")
            print(f"Kaggle Version ID: {version_id}")
            print("GitHub Actions Dispatch Sent: False")
            print("============================================================")
            return

        publish_service = DatasetPublishService(settings=settings)
        try:
            result = await publish_service.publish(session, target_dataset.id)
            print("\n============================================================")
            print("Publish successful.")
            print(f"Kaggle URL: {result.kaggle_url}")
            print(f"Kaggle Version ID: {result.kaggle_version_id}")
            print(f"GitHub Actions Dispatch Sent: {result.github_dispatch_sent}")
            print("============================================================")
        except GitHubDispatchPublishError as exc:
            print("\n============================================================")
            print("Kaggle publish succeeded, but GitHub dispatch failed.")
            print(f"Kaggle Version ID: {exc.kaggle_version_id}")
            print(
                "Kaggle URL: "
                f"https://www.kaggle.com/datasets/{exc.kaggle_slug}/versions/"
                f"{exc.kaggle_version_id}"
            )
            print(f"GitHub dispatch error detail: {exc}")
            print("============================================================")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"Publish failed: {exc}")
        sys.exit(1)
