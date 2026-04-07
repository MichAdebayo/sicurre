from __future__ import annotations

from db.models.lineage import NormalizedLabel
from data_platform.services.historical_stage_two import HistoricalStageTwoService


def test_historical_stage_two_maps_labels() -> None:
    assert (
        HistoricalStageTwoService.map_label({"source": "synthetic_phishing_medium"})
        is NormalizedLabel.PHISHING
    )
    assert (
        HistoricalStageTwoService.map_label({"source": "crowdsourced_spam_spam_3"})
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
