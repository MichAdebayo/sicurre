from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any


class CommonCrawlPromotionReviewService:
    DEFAULT_APPROVED_SUBTYPES = (
        "transactional_legitimate",
        "instructional_legitimate",
        "promotional_spam",
    )

    @classmethod
    def build_plan(
        cls,
        review_payload: dict[str, Any],
        *,
        approved_subtypes: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        approved = approved_subtypes or cls.DEFAULT_APPROVED_SUBTYPES
        samples = cls._collect_samples(review_payload)
        autopromotable: list[dict[str, Any]] = []
        manual_review: list[dict[str, Any]] = []
        quality_by_subtype: dict[str, dict[str, Any]] = {}

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in samples:
            subtype = sample.get("route_subtype")
            if subtype:
                grouped[str(subtype)].append(sample)

            if subtype not in approved:
                continue
            if sample.get("route_outcome") == "accepted":
                autopromotable.append(sample)
            elif sample.get("route_outcome") == "specialized_processing":
                manual_review.append(sample)

        for subtype, subtype_samples in grouped.items():
            quality_by_subtype[subtype] = cls._build_quality_metrics(subtype_samples)

        return {
            "mode": "no_write_promotion_review",
            "source_name": review_payload.get("source_name"),
            "approved_subtypes": list(approved),
            "reviewed_sample_count": len(samples),
            "autopromotable_count": len(autopromotable),
            "manual_review_count": len(manual_review),
            "autopromotable_record_ids": [
                sample["raw_record_id"] for sample in autopromotable
            ],
            "manual_review_record_ids": [
                sample["raw_record_id"] for sample in manual_review
            ],
            "quality_by_subtype": quality_by_subtype,
            "route_summary": cls._merge_source_summaries(
                review_payload, "route_summary"
            ),
            "subtype_summary": cls._merge_source_summaries(
                review_payload, "subtype_summary"
            ),
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

    @staticmethod
    def _build_quality_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
        similarities = [
            sample["similarity_score"]
            for sample in samples
            if isinstance(sample.get("similarity_score"), (int, float))
        ]
        normalized_lengths = [
            sample["normalized_length"]
            for sample in samples
            if isinstance(sample.get("normalized_length"), int)
        ]
        transformation_summary = Counter(
            str(sample.get("transformation_strength"))
            for sample in samples
            if sample.get("transformation_strength")
        )
        promotion_eligible_count = len(
            [
                sample
                for sample in samples
                if bool((sample.get("derived_payload") or {}).get("promotion_eligible"))
            ]
        )
        return {
            "sample_count": len(samples),
            "avg_similarity": round(mean(similarities), 3) if similarities else None,
            "avg_normalized_length": (
                round(mean(normalized_lengths), 1) if normalized_lengths else None
            ),
            "major_transformation_count": transformation_summary.get("major", 0),
            "promotion_eligible_count": promotion_eligible_count,
            "transformation_summary": dict(transformation_summary),
        }
