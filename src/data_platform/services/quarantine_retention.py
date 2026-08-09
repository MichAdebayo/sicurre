"""Retention enforcement for expired quarantine messages."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

Query = Callable[[str, tuple[Any, ...]], Awaitable[list[dict[str, Any]]]]
logger = logging.getLogger(__name__)


class QuarantineObjectStore(Protocol):
    """Minimal storage contract required by retention enforcement."""

    async def delete(self, storage_uri: str) -> None:
        """Delete one quarantined object."""


@dataclass(frozen=True, slots=True)
class QuarantinePurgeResult:
    """Aggregate outcome of one bounded quarantine purge pass."""

    candidates: int
    purged: int
    failed: int


async def purge_expired_quarantine(
    *,
    query: Query,
    store: QuarantineObjectStore,
    workspace_id: str | None = None,
    now: datetime | None = None,
) -> QuarantinePurgeResult:
    """Delete expired MIME objects and scrub their retained application metadata."""
    cutoff = (now or datetime.now(UTC)).isoformat()
    sql = (
        "SELECT id, workspace_id, raw_storage_uri FROM app_quarantine_item "
        "WHERE expires_at < ? AND status = 'held'"
    )
    params: tuple[Any, ...] = (cutoff,)
    if workspace_id is not None:
        sql += " AND workspace_id = ?"
        params += (workspace_id,)

    expired = await query(sql, params)
    purged = 0
    failed = 0
    for item in expired:
        storage_uri = item.get("raw_storage_uri")
        try:
            if storage_uri:
                await store.delete(str(storage_uri))
        except Exception:
            failed += 1
            logger.exception("Unable to delete expired quarantine object %s", item["id"])
            continue

        updated = await query(
            "UPDATE app_quarantine_item SET status = 'deleted', sender = '[deleted]', "
            "subject = '[deleted]', body_text = '', raw_storage_uri = NULL, "
            "raw_content_hash = NULL, raw_size_bytes = NULL, last_delivery_error = NULL "
            "WHERE id = ? AND workspace_id = ? AND status = 'held' RETURNING id",
            (item["id"], item["workspace_id"]),
        )
        purged += int(bool(updated))

    return QuarantinePurgeResult(
        candidates=len(expired),
        purged=purged,
        failed=failed,
    )
