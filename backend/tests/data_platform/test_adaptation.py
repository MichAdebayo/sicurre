from __future__ import annotations

from pathlib import Path

import pandas as pd

from sicurre_api.domains.data_platform.services.adaptation import (
    DEFAULT_TARGET_PER_ARCHETYPE,
    EXPORT_COLUMNS,
    FrenchCulturalAdaptationService,
)


def test_attach_archetype_matches_detects_expected_patterns() -> None:
    service = FrenchCulturalAdaptationService(seed=42)
    dataframe = pd.DataFrame(
        {
            "text": [
                "Your tax refund is overdue and an audit is required for your tax return.",
                "We detected an unauthorized bank transaction and need you to verify your account immediately.",
            ],
            "source": ["setfit", "setfit"],
            "label": [1, 1],
        }
    )

    matched_df = service.attach_archetype_matches(dataframe)

    assert "dgfip_tax" in matched_df.iloc[0]["archetypes"]
    assert "banque_securite" in matched_df.iloc[1]["archetypes"]


def test_generate_and_export_adapted_dataset(tmp_path: Path) -> None:
    service = FrenchCulturalAdaptationService(seed=42)
    matched_df = pd.DataFrame(
        {
            "text": [
                "Your tax refund is overdue and an audit is required for your tax return.",
                "Your bank account has an unauthorized transaction and account verification is required.",
            ],
            "source": ["setfit", "setfit"],
            "archetypes": [["dgfip_tax"], ["banque_securite"]],
            "n_archetypes": [1, 1],
        }
    )

    generated_df = service.generate_all_adapted_emails(matched_df, target_per_archetype=2)
    deduplicated_df, removed_duplicates = service.deduplicate_generated(generated_df)
    summary = service.build_summary(
        matched_df,
        matched_df,
        deduplicated_df,
        removed_duplicates=removed_duplicates,
    )
    export_result = service.export_adapted_dataframe(deduplicated_df, tmp_path)

    assert len(generated_df) == 16
    assert set(EXPORT_COLUMNS).issubset(deduplicated_df.columns)
    assert summary.deduplicated_rows == len(deduplicated_df)
    assert summary.min_french_markers >= 1
    assert export_result.timestamped_path.exists()
    assert export_result.stable_path.exists()
