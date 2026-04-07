from __future__ import annotations

from collections import Counter
from typing import Any


class CertFRReviewStagingService:
    @classmethod
    def build_stage_payload(cls, review_payload: dict[str, Any]) -> dict[str, Any]:
        samples = cls._collect_samples(review_payload)
        staged = {
            "threat_intel": [],
            "synthetic_lure_candidate": [],
            "procedural_notification": [],
            "irrecoverable_holdout": [],
        }
        threat_intel_with_iocs = 0
        phishing_relevant_threat_intel = 0

        for sample in samples:
            subtype = str(sample.get("route_subtype") or "")
            if subtype in staged:
                staged[subtype].append(
                    {
                        "raw_record_id": sample.get("raw_record_id"),
                        "route_reason": sample.get("route_reason"),
                        "normalized_length": sample.get("normalized_length"),
                        "derived_payload": sample.get("derived_payload"),
                    }
                )

            derived_payload = sample.get("derived_payload") or {}
            if subtype == "threat_intel":
                ioc_counts = derived_payload.get("ioc_counts", {})
                if sum(int(value) for value in ioc_counts.values()) > 0:
                    threat_intel_with_iocs += 1
                if derived_payload.get("phishing_relevance") is True:
                    phishing_relevant_threat_intel += 1

        subtype_summary = cls._merge_source_summaries(review_payload, "subtype_summary")
        return {
            "mode": "no_write_certfr_staging_review",
            "source_name": review_payload.get("source_name"),
            "reviewed_sample_count": len(samples),
            "subtype_summary": subtype_summary,
            "ioc_enriched_threat_intel_samples": threat_intel_with_iocs,
            "phishing_relevant_threat_intel_samples": phishing_relevant_threat_intel,
            "synthetic_lure_candidate_count": len(staged["synthetic_lure_candidate"]),
            "staged_samples": staged,
            "rejection_summary": cls._merge_source_summaries(
                review_payload, "rejection_summary"
            ),
        }

    @staticmethod
    def _collect_samples(review_payload: dict[str, Any]) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        result = review_payload.get("result", {})
        for source_groups in result.get("parent_sources", {}).values():
            for group in source_groups:
                samples.extend(group.get("samples", []))
        return samples

    @staticmethod
    def _merge_source_summaries(
        review_payload: dict[str, Any],
        key: str,
    ) -> dict[str, int]:
        summary: Counter[str] = Counter()
        result = review_payload.get("result", {})
        for source_groups in result.get("parent_sources", {}).values():
            for group in source_groups:
                summary.update(group.get(key, {}))
        return dict(summary)
