from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from data_platform.cron_schedulers.database.run_sql_ingestion import (
    _resolve_class_counts,
)
from data_platform.services.database.cron_scenarios import (
    CRON_ARCHETYPE_SCENARIOS,
    CRON_ARCHETYPE_SCENARIOS_BY_CLASS,
)
from data_platform.services.database.cron_feed import append_cron_generation_batch


def _read_verdict_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT verdict, COUNT(*) FROM threat_log GROUP BY verdict ORDER BY verdict"
        ).fetchall()
        return {str(verdict): int(count) for verdict, count in rows}
    finally:
        conn.close()


def _read_source_datasets(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT DISTINCT source_dataset FROM threat_log").fetchall()
        return {str(value) for (value,) in rows}
    finally:
        conn.close()


def test_append_cron_generation_batch_generates_all_three_classes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test_external_threats.db"

    result = append_cron_generation_batch(
        db_url=f"sqlite:///{db_path}",
        class_counts={"phishing": 2, "spam": 3, "legitimate": 4},
        seed=123,
    )

    verdict_counts = _read_verdict_counts(db_path)
    source_datasets = _read_source_datasets(db_path)

    assert result.inserted_total == 9
    assert result.inserted_by_class == {
        "phishing": 2,
        "spam": 3,
        "legitimate": 4,
    }
    assert result.used_scenario_count == 9
    assert result.scenario_catalog_size == 30
    assert verdict_counts == {
        "legitimate": 4,
        "phishing": 2,
        "spam": 3,
    }
    assert any(
        dataset.startswith("database/faker/synthetic_phishing_")
        for dataset in source_datasets
    )
    assert any(
        dataset.startswith("database/faker/synthetic_spam_")
        for dataset in source_datasets
    )
    assert any(
        dataset.startswith("database/faker/synthetic_legitimate_")
        for dataset in source_datasets
    )


def test_append_cron_generation_batch_appends_without_replacing_existing_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test_external_threats.db"

    append_cron_generation_batch(
        db_url=f"sqlite:///{db_path}",
        class_counts={"phishing": 1, "spam": 1, "legitimate": 1},
        seed=11,
    )
    result = append_cron_generation_batch(
        db_url=f"sqlite:///{db_path}",
        class_counts={"phishing": 2, "spam": 0, "legitimate": 1},
        seed=22,
    )

    verdict_counts = _read_verdict_counts(db_path)

    assert result.inserted_total == 3
    assert verdict_counts == {
        "legitimate": 2,
        "phishing": 3,
        "spam": 1,
    }


def test_cron_reference_scenarios_target_thirty_balanced_coverages() -> None:
    assert len(CRON_ARCHETYPE_SCENARIOS) == 30
    assert {
        label: len(items) for label, items in CRON_ARCHETYPE_SCENARIOS_BY_CLASS.items()
    } == {
        "phishing": 10,
        "spam": 10,
        "legitimate": 10,
    }


def test_append_cron_generation_batch_can_cover_all_reference_scenarios(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test_external_threats.db"

    result = append_cron_generation_batch(
        db_url=f"sqlite:///{db_path}",
        class_counts={"phishing": 10, "spam": 10, "legitimate": 10},
        seed=2026,
    )

    assert result.inserted_total == 30
    assert result.used_scenario_count == 30
    assert len(result.inserted_by_scenario) == 30
    assert all(count == 1 for count in result.inserted_by_scenario.values())


def test_resolve_class_counts_supports_total_count_distribution() -> None:
    assert _resolve_class_counts(
        total_count=200,
        phishing_count=None,
        spam_count=None,
        legitimate_count=None,
        default_total_count=72,
        max_total_count=1000,
    ) == {
        "phishing": 67,
        "spam": 67,
        "legitimate": 66,
    }


def test_resolve_class_counts_rejects_mixed_total_and_explicit_counts() -> None:
    with pytest.raises(ValueError, match="either --total-count or explicit"):
        _resolve_class_counts(
            total_count=200,
            phishing_count=80,
            spam_count=None,
            legitimate_count=None,
            default_total_count=72,
            max_total_count=1000,
        )


def test_resolve_class_counts_uses_env_style_default_total_count() -> None:
    assert _resolve_class_counts(
        total_count=None,
        phishing_count=None,
        spam_count=None,
        legitimate_count=None,
        default_total_count=500,
        max_total_count=1000,
    ) == {
        "phishing": 167,
        "spam": 167,
        "legitimate": 166,
    }


def test_resolve_class_counts_rejects_totals_above_max() -> None:
    with pytest.raises(ValueError, match="exceeds max_total_count"):
        _resolve_class_counts(
            total_count=1200,
            phishing_count=None,
            spam_count=None,
            legitimate_count=None,
            default_total_count=72,
            max_total_count=1000,
        )
