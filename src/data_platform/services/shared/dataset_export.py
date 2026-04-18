from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from core.config import ROOT_DIR, get_settings


class DatasetExportService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.final_dir = ROOT_DIR / "data" / "final"
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

        for split in ["train", "val", "test"]:
            split_df = dataframe[dataframe["split_name"] == split].copy()
            if split_df.empty:
                print(f"  ⚠️  No data mapped to split: {split}")
                continue

            split_dir = self.final_dir / split
            split_dir.mkdir(parents=True, exist_ok=True)
            
            # Export CSV Data payload (only text + label needed for ML modeling)
            csv_path = split_dir / "dataset.csv"
            split_df[["text", "label"]].to_csv(csv_path, index=False)
            
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
                "class_weights": sample_weights
            }
            
            # Export metadata JSON payload
            json_path = split_dir / "metadata.json"
            json_path.write_text(json.dumps(metadata, indent=2))
            
            print(f"\n📁 Exported Split: [{split.upper()}] to {split_dir.relative_to(ROOT_DIR)}")
            print(f"   > Generated: dataset.csv      ({len(split_df):,} rows)")
            print(f"   > Generated: metadata.json    ({len(label_stats)} identified classes)")
            
        print("\n✅ Dataset export completed successfully!")
