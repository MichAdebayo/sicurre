"""Validate whether a new monthly dataset release should be built."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import Text, cast, func, select

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.database import AsyncSessionFactory  # noqa: E402
from db.models import DataAnnotation, DataDataset, DataNormalizedMessage  # noqa: E402

NO_CHANGES_EXIT_CODE = 3


def _require_release_configuration() -> None:
    settings = get_settings()
    required = {
        "KAGGLE_USERNAME": settings.kaggle_username,
        "KAGGLE_API_TOKEN": settings.kaggle_key,
        "KAGGLE_DATASET_SLUG": settings.kaggle_dataset_slug,
        "SICURRE_GITHUB_ML_REPO_OWNER": settings.github_ml_repo_owner,
        "SICURRE_GITHUB_ML_DISPATCH_TOKEN": settings.github_ml_dispatch_token,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing monthly release settings: {', '.join(missing)}")


async def main() -> None:
    """Exit with code three when the latest frozen dataset already covers all records."""
    _require_release_configuration()
    async with AsyncSessionFactory() as session:
        eligible_count = int(
            (
                await session.execute(
                    select(func.count(func.distinct(DataNormalizedMessage.id))).join(
                        DataAnnotation,
                        func.replace(cast(DataAnnotation.normalized_message_id, Text), "-", "")
                        == func.replace(cast(DataNormalizedMessage.id, Text), "-", ""),
                    )
                )
            ).scalar_one()
        )
        latest_item_count = int(
            (
                await session.execute(
                    select(DataDataset.item_count)
                    .where(DataDataset.status == "frozen")
                    .order_by(DataDataset.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            or 0
        )

    print({"eligible_count": eligible_count, "latest_frozen_count": latest_item_count})
    if eligible_count <= latest_item_count:
        raise SystemExit(NO_CHANGES_EXIT_CODE)


if __name__ == "__main__":
    asyncio.run(main())
