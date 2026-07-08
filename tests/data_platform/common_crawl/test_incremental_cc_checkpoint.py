from __future__ import annotations

from data_platform.extractors.incremental_cc_extractor import (
    CommonCrawlCheckpoint,
    IncrementalCommonCrawlExtractor,
)


def test_common_crawl_missing_indices_are_recent_first_with_lookback() -> None:
    indices = [
        "CC-MAIN-2026-27",
        "CC-MAIN-2026-22",
        "CC-MAIN-2026-18",
        "CC-MAIN-2026-13",
        "CC-MAIN-2025-08",
    ]
    checkpoint = CommonCrawlCheckpoint(
        last_completed_index=None,
        completed_indices=frozenset({"CC-MAIN-2026-27"}),
    )

    missing = IncrementalCommonCrawlExtractor._compute_missing_indices(
        indices,
        checkpoint=checkpoint,
        lookback_indices=3,
    )

    assert missing == ["CC-MAIN-2026-22", "CC-MAIN-2026-18"]


def test_common_crawl_legacy_checkpoint_marks_older_indices_complete() -> None:
    indices = [
        "CC-MAIN-2026-27",
        "CC-MAIN-2026-22",
        "CC-MAIN-2026-18",
        "CC-MAIN-2025-08",
        "CC-MAIN-2024-51",
    ]

    checkpoint = IncrementalCommonCrawlExtractor._checkpoint_from_state(
        {"last_completed_index": "CC-MAIN-2026-18"},
        all_indices=indices,
    )

    assert "CC-MAIN-2026-18" in checkpoint.completed_indices
    assert "CC-MAIN-2025-08" in checkpoint.completed_indices
    assert "CC-MAIN-2026-22" not in checkpoint.completed_indices
