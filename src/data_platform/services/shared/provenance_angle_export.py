from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from core.config import ROOT_DIR, get_settings


@dataclass(frozen=True, slots=True)
class ProvenanceAngle:
    name: str
    description: str
    include_groups: frozenset[str] | None = None
    exclude_groups: frozenset[str] | None = None
    analysis_only: bool = False


PROVENANCE_ANGLES: tuple[ProvenanceAngle, ...] = (
    ProvenanceAngle(
        name="current_frozen",
        description="Control export using the current frozen dataset as-is.",
    ),
    ProvenanceAngle(
        name="synthetic_db_only",
        description="Only legacy-db synthetic faker descendants.",
        include_groups=frozenset({"synthetic_db"}),
    ),
    ProvenanceAngle(
        name="native_external_only",
        description="Only native non-generated external sources.",
        include_groups=frozenset({"native_external"}),
    ),
    ProvenanceAngle(
        name="no_synthetic_db",
        description="Everything except legacy-db faker synthetic descendants.",
        exclude_groups=frozenset({"synthetic_db"}),
    ),
    ProvenanceAngle(
        name="no_generated_pipeline",
        description="Everything except explicit generation-pipeline rows.",
        exclude_groups=frozenset({"generated_pipeline"}),
    ),
    ProvenanceAngle(
        name="no_adapted_or_generated",
        description="Native external plus non-adapted, non-generated rows only.",
        exclude_groups=frozenset({"adapted_db", "generated_pipeline"}),
    ),
    ProvenanceAngle(
        name="adapted_db_only",
        description="Only adapted legacy-db descendants; phishing-only analysis slice.",
        include_groups=frozenset({"adapted_db"}),
        analysis_only=True,
    ),
    ProvenanceAngle(
        name="generated_pipeline_only",
        description="Only explicit generation-pipeline descendants; phishing-only analysis slice.",
        include_groups=frozenset({"generated_pipeline"}),
        analysis_only=True,
    ),
)


class ProvenanceAngleExportService:
    def __init__(self, output_root: Path | None = None) -> None:
        self.settings = get_settings()
        self.engine = create_engine(self.settings.sync_data_platform_database_url)
        self.output_root = output_root or ROOT_DIR / "data" / "final" / "provenance"

    def export_angles(self, version_tag: str | None = None) -> dict[str, str]:
        resolved_version_tag = version_tag or self._resolve_latest_version_tag()
        dataframe = self._load_dataset_rows(resolved_version_tag)
        if dataframe.empty:
            raise ValueError(
                f"No rows found for dataset version: {resolved_version_tag}"
            )

        self.output_root.mkdir(parents=True, exist_ok=True)

        export_summary: dict[str, str] = {}
        for angle in PROVENANCE_ANGLES:
            angle_df = self._filter_angle(dataframe, angle)
            angle_dir = self.output_root / angle.name
            angle_dir.mkdir(parents=True, exist_ok=True)

            metadata = self._build_metadata(
                dataframe=angle_df,
                version_tag=resolved_version_tag,
                angle=angle,
            )

            for split in ("train", "val", "test"):
                split_df = angle_df[angle_df["split_name"] == split].copy()
                export_path = angle_dir / f"sicurre_{split}.csv"
                split_df[["text", "label"]].to_csv(export_path, index=False)

            metadata_path = angle_dir / "metadata.json"
            metadata_path.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            export_summary[angle.name] = str(angle_dir)

        return export_summary

    def _resolve_latest_version_tag(self) -> str:
        query = text("""
            SELECT version_tag
            FROM data_dataset
            WHERE status = 'frozen'
            ORDER BY COALESCE(frozen_at, created_at) DESC, created_at DESC
            LIMIT 1
            """)
        with self.engine.connect() as conn:
            version_tag = conn.execute(query).scalar_one_or_none()

        if version_tag is None:
            raise ValueError("No frozen dataset version found in data_dataset")
        return str(version_tag)

    def _load_dataset_rows(self, version_tag: str) -> pd.DataFrame:
        query = text("""
            SELECT
                d.version_tag,
                d.name AS dataset_name,
                di.split_name,
                di.row_order,
                di.sample_weight,
                nm.id AS normalized_message_id,
                nm.normalized_text AS text,
                nm.current_label AS label,
                ss.name AS source_name,
                ss.source_type,
                CASE
                    WHEN rr.generation_sample_id IS NOT NULL THEN 'generated_pipeline'
                    WHEN ss.name LIKE 'database/faker/%' THEN 'synthetic_db'
                    WHEN ss.name LIKE 'database/adapted/%' THEN 'adapted_db'
                    WHEN ss.name = 'database-historical' THEN 'historical_db'
                    ELSE 'native_external'
                END AS provenance_group
            FROM data_dataset d
            JOIN data_dataset_item di ON di.dataset_id = d.id
            JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
            JOIN data_raw_record rr ON rr.id = nm.raw_record_id
            LEFT JOIN data_source_system ss ON ss.id = rr.source_system_id
            WHERE d.version_tag = :version_tag
            ORDER BY di.split_name ASC, di.row_order ASC, nm.id ASC
            """)
        with self.engine.connect() as conn:
            return pd.read_sql(query, conn, params={"version_tag": version_tag})

    def _filter_angle(
        self, dataframe: pd.DataFrame, angle: ProvenanceAngle
    ) -> pd.DataFrame:
        angle_df = dataframe
        if angle.include_groups is not None:
            angle_df = angle_df[angle_df["provenance_group"].isin(angle.include_groups)]
        if angle.exclude_groups is not None:
            angle_df = angle_df[
                ~angle_df["provenance_group"].isin(angle.exclude_groups)
            ]
        return angle_df.copy()

    def _build_metadata(
        self,
        *,
        dataframe: pd.DataFrame,
        version_tag: str,
        angle: ProvenanceAngle,
    ) -> dict[str, object]:
        split_summary: dict[str, dict[str, object]] = {}
        for split in ("train", "val", "test"):
            split_df = dataframe[dataframe["split_name"] == split]
            split_summary[split] = {
                "item_count": len(split_df),
                "label_distribution": {
                    str(label): count
                    for label, count in split_df["label"]
                    .value_counts()
                    .sort_index()
                    .items()
                },
                "provenance_distribution": {
                    str(group): count
                    for group, count in split_df["provenance_group"]
                    .value_counts()
                    .sort_index()
                    .items()
                },
            }

        train_labels = set(
            dataframe.loc[dataframe["split_name"] == "train", "label"]
            .astype(str)
            .tolist()
        )
        return {
            "version_tag": version_tag,
            "angle_name": angle.name,
            "description": angle.description,
            "analysis_only": angle.analysis_only,
            "trainable_three_class": train_labels == {"legitimate", "phishing", "spam"},
            "item_count": len(dataframe),
            "provenance_distribution": {
                str(group): count
                for group, count in dataframe["provenance_group"]
                .value_counts()
                .sort_index()
                .items()
            },
            "source_distribution": {
                str(source): count
                for source, count in dataframe["source_name"]
                .fillna("unknown")
                .value_counts()
                .items()
            },
            "splits": split_summary,
        }
