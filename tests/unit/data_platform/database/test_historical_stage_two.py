from __future__ import annotations

from data_platform.services.database.historical_stage_two import (
    HistoricalStageTwoService,
)
from db.models.lineage import NormalizedLabel


def test_historical_stage_two_maps_labels() -> None:
    assert (
        HistoricalStageTwoService.map_label({"source": "synthetic_phishing_medium"})
        is NormalizedLabel.PHISHING
    )
    assert (
        HistoricalStageTwoService.map_label(
            {"source": "database/faker/synthetic_spam_medium", "label": 0}
        )
        is NormalizedLabel.SPAM
    )
    assert (
        HistoricalStageTwoService.map_label({"source": "crowdsourced_spam_spam_3"})
        is NormalizedLabel.SPAM
    )


def test_historical_stage_two_maps_raw_spam_label() -> None:
    assert (
        HistoricalStageTwoService.map_label(
            {"source": "database/custom/manual_review", "label": "spam"}
        )
        is NormalizedLabel.SPAM
    )


def test_historical_stage_two_routes_thin_spam_to_specialized_processing() -> None:
    result = HistoricalStageTwoService.review(
        "Bonjour offre limitée",
        {"source": "crowdsourced_spam_spam_3"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "historical_content_too_thin"
    assert result.derived_payload is not None
    assert result.derived_payload["quality_gate_passed"] is False


def test_historical_stage_two_preserves_database_path_provenance() -> None:
    raw_content = {"source": "database/faker/synthetic_phishing_medium", "label": 0}

    assert HistoricalStageTwoService.map_label(raw_content) is NormalizedLabel.PHISHING

    result = HistoricalStageTwoService.review(
        "Bonjour, veuillez confirmer votre compte immédiatement.",
        raw_content,
    )

    assert result.derived_payload is not None
    assert result.derived_payload["historical_source_path"] == (
        "database/faker/synthetic_phishing_medium"
    )
    assert result.derived_payload["historical_source_family"] == "faker"
    assert result.derived_payload["historical_subsource"] == "synthetic_phishing_medium"
