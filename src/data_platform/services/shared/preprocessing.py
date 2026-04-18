from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_platform.cleaning.normalization import (
    DEDUP_HASH_LEN,
    MIN_TEXT_LEN,
    TextNormalizationService,
    dedup_sha256,
)


OUTPUT_COLS: list[str] = [
    "text",
    "label",
    "source",
    "language",
    "archetype",
    "text_len",
]


@dataclass(frozen=True, slots=True)
class DataFrameProcessingResult:
    dataframe: pd.DataFrame
    dropped_short: int
    dropped_duplicate: int


class DataFramePreprocessingService:
    def __init__(
        self,
        normalization_service: TextNormalizationService | None = None,
    ) -> None:
        self.normalization_service = normalization_service or TextNormalizationService()

    def process_dataframe(
        self,
        dataframe: pd.DataFrame,
        *,
        text_column: str = "text",
    ) -> DataFrameProcessingResult:
        df = dataframe.copy()
        artifacts = (
            df[text_column].astype(str).apply(self.normalization_service.normalize_text)
        )
        df[text_column] = artifacts.apply(lambda item: item.cleaned_text)
        df["text_len"] = artifacts.apply(lambda item: item.text_length)

        before = len(df)
        df = df[df["text_len"] >= MIN_TEXT_LEN].reset_index(drop=True)
        dropped_short = before - len(df)

        df["_hash"] = df[text_column].apply(dedup_sha256)
        before_dedup = len(df)
        df = (
            df.drop_duplicates(subset="_hash", keep="first")
            .drop(columns="_hash")
            .reset_index(drop=True)
        )
        dropped_duplicate = before_dedup - len(df)

        return DataFrameProcessingResult(
            dataframe=df,
            dropped_short=dropped_short,
            dropped_duplicate=dropped_duplicate,
        )


def save_processed_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output_df = df.copy()
    for column in OUTPUT_COLS:
        if column not in output_df.columns:
            output_df[column] = ""
    output_df[OUTPUT_COLS].to_csv(path, index=False)
