from __future__ import annotations

import asyncio
import json

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from core.config import ROOT_DIR, get_settings
from data_platform.services.shared.dataset_manifest import build_dataset_manifest
from data_platform.services.shared.snapshot_storage import build_snapshot_store


#: Written when provenance could not be read. It is an explicit statement in
#: the manifest rather than a missing key, so a consumer can tell "this split
#: came from nowhere" from "we did not manage to look".
_UNAVAILABLE_PROVENANCE = {
    "available": False,
    "reason": "provenance tables could not be read",
}


def _split_provenance(split_df: "pd.DataFrame") -> dict:
    """Per-source counts for one split, for the sidecar manifest."""
    frame = split_df.assign(source_name=split_df["source_name"].fillna("unattributed"))
    counts = frame["source_name"].value_counts()
    by_source = {str(name): int(count) for name, count in counts.items()}

    by_source_and_label: dict[str, dict[str, int]] = {}
    for (name, label), count in frame.groupby(["source_name", "label"]).size().items():
        by_source_and_label.setdefault(str(name), {})[str(label)] = int(count)

    return {
        "available": True,
        "by_source": by_source,
        "by_source_and_label": by_source_and_label,
        "source_count": len(by_source),
        "unattributed": by_source.get("unattributed", 0),
    }


class DatasetExportService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.final_dir = ROOT_DIR / "data" / "final"
        self.export_prefix = self.settings.training_dataset_snapshot_prefix.strip("/")
        self.snapshot_store = build_snapshot_store(
            local_root_dir=self.final_dir,
            repo_root=ROOT_DIR,
            source_key="training_dataset",
        )
        # We use a sync engine specifically tailored to fast dataframe exports
        self.engine = create_engine(self.settings.sync_data_platform_database_url)

    def _read_provenance(self, conn, version_tag: str, *, sqlite: bool) -> dict[str, dict]:
        """Per-split source counts, read separately from the dataset itself."""
        message_join = (
            "di.normalized_message_id = replace(nm.id, '-', '')"
            if sqlite
            else "di.normalized_message_id = nm.id"
        )
        # Both sides of this one are stored the same way, so it joins directly.
        raw_join = "nm.raw_record_id = rr.id"
        # This one genuinely differs: data_source_system stores its id without dashes under SQLite.
        source_join = (
            "replace(rr.source_system_id, '-', '') = ss.id"
            if sqlite
            else "rr.source_system_id = ss.id"
        )
        query = text(f"""
            SELECT
                di.split_name,
                nm.current_label as label,
                ss.name as source_name
            FROM data_dataset d
            JOIN data_dataset_item di ON d.id = di.dataset_id
            JOIN data_normalized_message nm ON {message_join}
            LEFT JOIN data_raw_record rr ON {raw_join}
            LEFT JOIN data_source_system ss ON {source_join}
            WHERE d.version_tag = :version_tag
        """)

        try:
            frame = pd.read_sql(query, conn, params={"version_tag": version_tag})
        except SQLAlchemyError as exc:
            print(f"  ⚠️  Provenance unavailable, exporting without it: {type(exc).__name__}")
            return {}

        return {
            str(split): _split_provenance(rows)
            for split, rows in frame.groupby("split_name")
        }

    def export_dataset(self, version_tag: str) -> None:
        print("=" * 60)
        print(f"SICURRE — Export ML Dataset Version: {version_tag}")
        print("=" * 60)

        sqlite = self.engine.dialect.name == "sqlite"
        message_join = (
            "di.normalized_message_id = replace(nm.id, '-', '')"
            if sqlite
            else "di.normalized_message_id = nm.id"
        )
        query = text(f"""
            SELECT
                d.id as dataset_id,
                d.name as dataset_name,
                d.item_count,
                di.split_name,
                di.sample_weight,
                nm.normalized_text as text,
                nm.current_label as label
            FROM data_dataset d
            JOIN data_dataset_item di ON d.id = di.dataset_id
            JOIN data_normalized_message nm ON {message_join}
            WHERE d.version_tag = :version_tag
            ORDER BY di.row_order ASC
        """)

        with self.engine.connect() as conn:
            dataframe = pd.read_sql(query, conn, params={"version_tag": version_tag})
            provenance = self._read_provenance(conn, version_tag, sqlite=sqlite)

        if dataframe.empty:
            raise ValueError(f"No records found for dataset version: {version_tag}")

        export_results: list[dict[str, str]] = []
        split_payloads: dict[str, bytes] = {}
        for split in ["train", "val", "test"]:
            split_df = dataframe[dataframe["split_name"] == split].copy()
            if split_df.empty:
                print(f"  ⚠️  No data mapped to split: {split}")
                continue

            # Calculate metadata payload dynamically
            label_stats = split_df["label"].value_counts().to_dict()
            sample_weights = (
                split_df.drop_duplicates(subset=["label"])
                .set_index("label")["sample_weight"]
                .to_dict()
            )

            metadata = {
                "version_tag": version_tag,
                "dataset_name": str(split_df["dataset_name"].iloc[0]),
                "split": split,
                "item_count": len(split_df),
                "class_distribution": label_stats,
                "class_weights": sample_weights,
                "provenance": provenance.get(split, _UNAVAILABLE_PROVENANCE),
            }

            csv_payload = split_df[["text", "label"]].to_csv(index=False).encode("utf-8")
            split_payloads[split] = csv_payload
            json_payload = json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8")

            export_results.append(
                asyncio.run(
                    self._export_split_payloads(
                        version_tag=version_tag,
                        split=split,
                        csv_payload=csv_payload,
                        json_payload=json_payload,
                    )
                )
            )

            print(
                f"\n📁 Exported Split: [{split.upper()}] to raw-snapshots/{self.export_prefix}/{version_tag}/{split}"
            )
            print(f"   > Generated: dataset.csv      ({len(split_df):,} rows)")
            print(f"   > Generated: metadata.json    ({len(label_stats)} identified classes)")
        for result in export_results:
            print(f"   > CSV URI : {result['csv_uri']}")
            print(f"   > JSON URI: {result['json_uri']}")

        manifest_payload, manifest_checksum = build_dataset_manifest(
            dataset_id=str(dataframe["dataset_id"].iloc[0]),
            version_tag=version_tag,
            item_count=len(dataframe),
            split_payloads=split_payloads,
        )
        manifest_uri = asyncio.run(
            self._export_manifest(version_tag=version_tag, payload=manifest_payload)
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE data_dataset
                    SET artifact_uri = :artifact_uri,
                        content_checksum = :content_checksum,
                        schema_version = :schema_version
                    WHERE version_tag = :version_tag
                    """
                ),
                {
                    "artifact_uri": manifest_uri,
                    "content_checksum": manifest_checksum,
                    "schema_version": "1",
                    "version_tag": version_tag,
                },
            )
        print(f"   > Manifest URI: {manifest_uri}")
        print(f"   > Manifest SHA-256: {manifest_checksum}")

        print("\n✅ Dataset export completed successfully!")

    async def _export_split_payloads(
        self,
        *,
        version_tag: str,
        split: str,
        csv_payload: bytes,
        json_payload: bytes,
    ) -> dict[str, str]:
        source_prefix = f"{self.export_prefix}/{version_tag}/{split}"
        csv_key = self.snapshot_store.build_object_key(
            source_prefix=source_prefix,
            filename="dataset.csv",
        )
        json_key = self.snapshot_store.build_object_key(
            source_prefix=source_prefix,
            filename="metadata.json",
        )
        csv_result = await self.snapshot_store.write_snapshot(
            object_key=csv_key,
            payload=csv_payload,
            content_type="text/csv; charset=utf-8",
        )
        json_result = await self.snapshot_store.write_snapshot(
            object_key=json_key,
            payload=json_payload,
            content_type="application/json; charset=utf-8",
        )
        return {"csv_uri": csv_result.storage_uri, "json_uri": json_result.storage_uri}

    async def _export_manifest(self, *, version_tag: str, payload: bytes) -> str:
        """Persist the canonical manifest above the split object prefixes."""
        key = self.snapshot_store.build_object_key(
            source_prefix=f"{self.export_prefix}/{version_tag}",
            filename="dataset-manifest.json",
        )
        result = await self.snapshot_store.write_snapshot(
            object_key=key,
            payload=payload,
            content_type="application/json; charset=utf-8",
        )
        return result.storage_uri
