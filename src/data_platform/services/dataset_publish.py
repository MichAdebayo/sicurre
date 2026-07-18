from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from data_platform.services.shared.github_actions_gateway import (
    GitHubActionsGateway,
    GitHubDispatchError,
)
from data_platform.services.shared.kaggle_gateway import (
    KaggleGateway,
    KagglePushError,
    write_split_csv,
)
from db.models.lineage import DatasetStatus, SplitName
from db.queries.records import DatasetNotFoundError, DatasetQueries

logger = logging.getLogger(__name__)

_SPLITS = [s.value for s in SplitName]


class DatasetNotFrozenError(Exception):
    """Raised when publish is attempted on a non-frozen dataset."""


class DatasetPublishConfigError(Exception):
    """Raised when publish feature is not configured (missing secrets)."""


class KagglePushPublishError(Exception):
    """Raised when the Kaggle push step fails (wraps KagglePushError)."""

    def __init__(self, cause: KagglePushError) -> None:
        super().__init__(str(cause))
        self.cause = cause


class GitHubDispatchPublishError(Exception):
    """Raised when GitHub dispatch fails after Kaggle push succeeded."""

    def __init__(
        self,
        cause: GitHubDispatchError,
        *,
        kaggle_version_id: int,
        kaggle_slug: str,
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.kaggle_version_id = kaggle_version_id
        self.kaggle_slug = kaggle_slug


@dataclass(frozen=True)
class DatasetPublishResult:
    kaggle_url: str
    kaggle_version_id: int
    github_dispatch_sent: bool


def kaggle_dataset_url(slug: str, version_id: int) -> str:
    """Return a valid Kaggle URL even when its client omits the version number."""
    base_url = f"https://www.kaggle.com/datasets/{slug}"
    return f"{base_url}/versions/{version_id}" if version_id > 0 else base_url


class DatasetPublishService:
    """Orchestrates publishing a frozen DataDataset.

    Sequence (all steps must succeed or the chain stops):
      1. Validate: dataset exists + status is FROZEN + secrets configured
      2. Export CSVs to a temp dir  (one file per split)
      3. kaggle datasets version   (KaggleGateway — thread executor)
      4. Write kaggle_version_id + published_at to DB  (best-effort, warn on failure)
      5. GitHub workflow_dispatch  (GitHubActionsGateway — async httpx)
      6. Return DatasetPublishResult
    """

    def __init__(
        self,
        settings: Settings,
        queries: DatasetQueries | None = None,
    ) -> None:
        self._settings = settings
        self._queries = queries or DatasetQueries()

    def _require_secrets(self) -> tuple[KaggleGateway, GitHubActionsGateway]:
        cfg = self._settings
        missing: list[str] = []
        if not cfg.kaggle_username:
            missing.append("KAGGLE_USERNAME")
        if not cfg.kaggle_key:
            missing.append("KAGGLE_API_TOKEN")
        if not cfg.kaggle_dataset_slug:
            missing.append("KAGGLE_DATASET_SLUG")
        if not cfg.github_ml_dispatch_token:
            missing.append("SICURRE_GITHUB_ML_DISPATCH_TOKEN")
        if not cfg.github_ml_repo_owner:
            missing.append("SICURRE_GITHUB_ML_REPO_OWNER")
        if missing:
            raise DatasetPublishConfigError(
                f"Dataset publish not configured: missing {', '.join(missing)}"
            )
        kaggle_gw = KaggleGateway(
            username=str(cfg.kaggle_username),
            key=str(cfg.kaggle_key),
        )
        github_gw = GitHubActionsGateway(
            token=str(cfg.github_ml_dispatch_token),
            owner=str(cfg.github_ml_repo_owner),
            repo=cfg.github_ml_repo_name,
        )
        return kaggle_gw, github_gw

    async def publish(
        self,
        session: AsyncSession,
        dataset_id: UUID,
    ) -> DatasetPublishResult:
        cfg = self._settings

        # ── 1. Validate ───────────────────────────────────────────────────────
        kaggle_gw, github_gw = self._require_secrets()
        dataset = await self._queries.get(session, dataset_id)

        if dataset.status != DatasetStatus.FROZEN.value:
            raise DatasetNotFrozenError(
                f"Dataset {dataset_id} is not FROZEN (status={dataset.status}). "
                "Only frozen datasets can be published."
            )

        # ── 2. Export CSVs ───────────────────────────────────────────────────
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = Path(tmp)
            for split in _SPLITS:
                rows_raw = await self._queries.list_items_for_export(
                    session, dataset_id, split_name=split
                )
                if rows_raw:
                    rows = [{"text": text, "label": label} for text, label in rows_raw]
                    write_split_csv(rows, export_dir / f"{split}.csv")

            # ── 3. kaggle datasets version ───────────────────────────────────
            slug = str(cfg.kaggle_dataset_slug)
            try:
                kaggle_version_id = await kaggle_gw.push_version(
                    slug=slug,
                    export_dir=export_dir,
                    message=f"Dataset {dataset.version_tag} — auto-publish",
                )
            except KagglePushError as exc:
                raise KagglePushPublishError(exc) from exc

        # ── 4. Write publish result to DB (best-effort) ──────────────────────
        published_at = datetime.now(timezone.utc)
        try:
            await self._queries.update_publish_result(
                session,
                dataset_id,
                kaggle_version_id=kaggle_version_id,
                published_at=published_at,
            )
        except Exception:
            logger.warning(
                "publish: DB update failed for dataset %s (kaggle_version_id=%d). "
                "Kaggle push already succeeded — continuing to dispatch.",
                dataset_id,
                kaggle_version_id,
            )

        # ── 5. GitHub workflow_dispatch ──────────────────────────────────────
        try:
            await github_gw.dispatch_training(kaggle_slug=slug)
        except GitHubDispatchError as exc:
            raise GitHubDispatchPublishError(
                exc,
                kaggle_version_id=kaggle_version_id,
                kaggle_slug=slug,
            ) from exc

        # ── 6. Return result ─────────────────────────────────────────────────
        kaggle_url = kaggle_dataset_url(slug, kaggle_version_id)
        return DatasetPublishResult(
            kaggle_url=kaggle_url,
            kaggle_version_id=kaggle_version_id,
            github_dispatch_sent=True,
        )
