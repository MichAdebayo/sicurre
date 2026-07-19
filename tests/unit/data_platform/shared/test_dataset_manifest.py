"""Canonical frozen-dataset manifest tests."""

from __future__ import annotations

import hashlib
import json

from data_platform.services.shared.dataset_manifest import build_dataset_manifest


def test_dataset_manifest_is_deterministic_and_content_addressed() -> None:
    """Split ordering cannot change the frozen dataset identity."""
    first, first_checksum = build_dataset_manifest(
        dataset_id="dataset-id",
        version_tag="base-v1",
        item_count=3,
        split_payloads={"test": b"test", "train": b"train", "val": b"val"},
    )
    second, second_checksum = build_dataset_manifest(
        dataset_id="dataset-id",
        version_tag="base-v1",
        item_count=3,
        split_payloads={"train": b"train", "val": b"val", "test": b"test"},
    )
    manifest = json.loads(first)
    assert first == second
    assert first_checksum == second_checksum == hashlib.sha256(first).hexdigest()
    assert list(manifest["splits"]) == ["test", "train", "val"]
    assert manifest["splits"]["train"]["sha256"] == hashlib.sha256(b"train").hexdigest()
