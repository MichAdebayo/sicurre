"""Canonical frozen-dataset manifest construction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from uuid import UUID


def build_dataset_manifest(
    *,
    dataset_id: UUID | str,
    version_tag: str,
    item_count: int,
    split_payloads: Mapping[str, bytes],
) -> tuple[bytes, str]:
    """Return canonical manifest bytes and their SHA-256 identity."""
    splits = {
        split: {
            "filename": f"{split}.csv",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
        for split, payload in sorted(split_payloads.items())
    }
    manifest = {
        "schema_version": "1",
        "dataset_id": str(dataset_id),
        "version_tag": version_tag,
        "item_count": item_count,
        "splits": splits,
    }
    payload = json.dumps(
        manifest, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()
    return payload, hashlib.sha256(payload).hexdigest()
