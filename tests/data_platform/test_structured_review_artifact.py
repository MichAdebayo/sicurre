from __future__ import annotations

import json

from data_platform.services.structured_review_artifact import (
    StructuredReviewArtifactService,
)


def test_structured_review_artifact_writes_json(tmp_path) -> None:
    output_path = tmp_path / "review.json"
    payload = StructuredReviewArtifactService.build_payload(
        result={"status": "review success", "parent_sources": {}},
        source_name="cert-fr-cti",
        source_type="scraping",
        route_outcome_filter="specialized_processing",
        route_subtype_filter="threat_intel",
    )

    StructuredReviewArtifactService.write_json(output_path, payload)

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["source_name"] == "cert-fr-cti"
    assert saved["route_subtype_filter"] == "threat_intel"
    assert saved["result"]["status"] == "review success"


def test_structured_review_artifact_reads_json(tmp_path) -> None:
    output_path = tmp_path / "review.json"
    output_path.write_text('{"status": "ok"}', encoding="utf-8")

    saved = StructuredReviewArtifactService.read_json(output_path)

    assert saved["status"] == "ok"
