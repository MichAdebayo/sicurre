"""Rebuild readable quarantine previews from the stored raw MIME.

Held items quarantined before 13 September 2026 kept the Worker's rough
projection of the message as their preview: raw headers, and bodies still
quoted-printable or base64 encoded. For each held item whose raw MIME is in
custody, the preview is decoded again, masked and capped as at intake. An
unchanged preview is not rewritten, so the command is safe to run on every
deploy.
"""

from __future__ import annotations

import asyncio
import logging

from core.config import get_settings
from core.mime_headers import extract_mime_body
from data_platform.cleaning.normalization import anonymize_pii
from data_platform.services.quarantine_storage import build_quarantine_store
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)


async def rebuild_previews() -> dict[str, int]:
    """Re-decode the preview of every held item with raw MIME; return the counts."""
    store = build_quarantine_store(get_settings())
    rows = await execute_runtime_query(
        "SELECT id, raw_storage_uri, body_text FROM app_quarantine_item "
        "WHERE status = 'held' AND raw_storage_uri IS NOT NULL AND raw_storage_uri <> ''"
    )
    counts = {"held_with_raw": len(rows), "rebuilt": 0, "unchanged": 0, "failed": 0}
    for row in rows:
        try:
            raw = await store.read(str(row["raw_storage_uri"]))
            readable = extract_mime_body(raw.decode("utf-8", errors="replace"))
            preview = anonymize_pii(readable)[:4000] if readable.strip() else ""
            if not preview or preview == row.get("body_text"):
                counts["unchanged"] += 1
                continue
            await execute_runtime_query(
                "UPDATE app_quarantine_item SET body_text = ? WHERE id = ? AND status = 'held'",
                (preview, row["id"]),
            )
            counts["rebuilt"] += 1
        except Exception as exc:  # one unreadable object must not stop the others
            counts["failed"] += 1
            logger.warning(
                "Could not rebuild the preview of quarantine item %s: %s",
                row["id"],
                type(exc).__name__,
            )
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(f"quarantine previews: {asyncio.run(rebuild_previews())}")


if __name__ == "__main__":
    main()
