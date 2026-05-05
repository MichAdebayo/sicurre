from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from core.config import ROOT_DIR, get_settings
from data_platform.services.shared.snapshot_storage import build_snapshot_store


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
        self.engine = create_engine(self.settings.sync_database_url)

    def export_dataset(self, version_tag: str) -> None:
        print("=" * 60)
        print(f"SICURRE — Export ML Dataset Version: {version_tag}")
        print("=" * 60)

        query = text("""
            SELECT 
                d.name as dataset_name,
                d.item_count,
                di.split_name,
                di.sample_weight,
                nm.normalized_text as text,
                nm.current_label as label
            FROM data_dataset d
            JOIN data_dataset_item di ON d.id = di.dataset_id
            JOIN data_normalized_message nm ON di.normalized_message_id = nm.id
            WHERE d.version_tag = :version_tag
            ORDER BY di.row_order ASC
        """)

        with self.engine.connect() as conn:
            dataframe = pd.read_sql(query, conn, params={"version_tag": version_tag})

        if dataframe.empty:
            raise ValueError(f"No records found for dataset version: {version_tag}")

        export_results: list[dict[str, str]] = []
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
            }

            csv_payload = (
                split_df[["text", "label"]].to_csv(index=False).encode("utf-8")
            )
            json_payload = json.dumps(metadata, indent=2, ensure_ascii=False).encode(
                "utf-8"
            )

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
            print(
                f"   > Generated: metadata.json    ({len(label_stats)} identified classes)"
            )
        for result in export_results:
            print(f"   > CSV URI : {result['csv_uri']}")
            print(f"   > JSON URI: {result['json_uri']}")

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
