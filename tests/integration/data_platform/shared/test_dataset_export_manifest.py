"""Frozen export manifest persistence test."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text

from data_platform.services.shared.dataset_export import DatasetExportService
from data_platform.services.shared.snapshot_storage import LocalSnapshotStore


def test_dataset_export_persists_canonical_manifest(tmp_path: Path) -> None:
    """R2-equivalent export metadata is written back to data_dataset."""
    database_path = tmp_path / "export.db"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE data_dataset (
                    id TEXT PRIMARY KEY, name TEXT, version_tag TEXT,
                    item_count INTEGER, artifact_uri TEXT,
                    content_checksum TEXT, schema_version TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE data_dataset_item (
                    dataset_id TEXT, normalized_message_id TEXT,
                    split_name TEXT, sample_weight REAL, row_order INTEGER
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE data_normalized_message (
                    id TEXT PRIMARY KEY, normalized_text TEXT, current_label TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO data_dataset (id, name, version_tag, item_count)
                VALUES ('dataset1', 'sicurre-data', 'base-v1', 3)
                """
            )
        )
        for index, split in enumerate(("train", "val", "test"), start=1):
            connection.execute(
                text(
                    """
                    INSERT INTO data_normalized_message
                    (id, normalized_text, current_label)
                    VALUES (:id, :message, :label)
                    """
                ),
                {"id": f"message{index}", "message": f"mail {index}", "label": "legitimate"},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO data_dataset_item
                    (dataset_id, normalized_message_id, split_name, sample_weight, row_order)
                    VALUES ('dataset1', :message_id, :split, 1.0, :row_order)
                    """
                ),
                {"message_id": f"message{index}", "split": split, "row_order": index},
            )

    export_root = tmp_path / "exports"
    service = object.__new__(DatasetExportService)
    service.final_dir = export_root
    service.export_prefix = "training_dataset"
    service.snapshot_store = LocalSnapshotStore(root_dir=export_root, repo_root=tmp_path)
    service.engine = engine

    service.export_dataset("base-v1")

    manifest_path = export_root / "training_dataset/base-v1/dataset-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["dataset_id"] == "dataset1"
    assert manifest["item_count"] == 3
    assert set(manifest["splits"]) == {"train", "val", "test"}
    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT artifact_uri, content_checksum, schema_version
                FROM data_dataset WHERE version_tag = 'base-v1'
                """
            )
        ).one()
    assert row.artifact_uri.endswith("dataset-manifest.json")
    assert len(row.content_checksum) == 64
    assert row.schema_version == "1"
    engine.dispose()
