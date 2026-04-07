from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


class StageTwoActionArtifactsService:
    @classmethod
    def build_artifacts(
        cls,
        *,
        matrix_payload: dict[str, Any],
        review_payloads: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        samples_by_source = cls._collect_samples_by_source(review_payloads)

        adaptation_sources: list[dict[str, Any]] = []
        signal_sources: list[dict[str, Any]] = []
        archive_sources: list[dict[str, Any]] = []
        adaptation_total = 0
        signal_total = 0
        archive_total = 0

        for source in matrix_payload.get("sources", []):
            source_name = str(source.get("source_name") or "unknown")
            source_samples = samples_by_source.get(source_name, [])

            adaptation_rules = cls._build_rule_payloads(
                source_name=source_name,
                rules=source.get("rows", []),
                source_samples=source_samples,
                action="adapt",
            )
            signal_rules = cls._build_rule_payloads(
                source_name=source_name,
                rules=source.get("rows", []),
                source_samples=source_samples,
                action="extract_signals_only",
            )
            archive_rules = cls._build_rule_payloads(
                source_name=source_name,
                rules=source.get("rows", []),
                source_samples=source_samples,
                action="archive",
            )

            if adaptation_rules:
                adaptation_sources.append(
                    {
                        "source_name": source_name,
                        "rules": adaptation_rules,
                    }
                )
                adaptation_total += sum(
                    int(rule.get("current_count", 0)) for rule in adaptation_rules
                )

            if signal_rules:
                signal_sources.append(
                    {
                        "source_name": source_name,
                        "rules": signal_rules,
                    }
                )
                signal_total += sum(
                    int(rule.get("current_count", 0)) for rule in signal_rules
                )

            if archive_rules:
                archive_sources.append(
                    {
                        "source_name": source_name,
                        "rules": archive_rules,
                    }
                )
                archive_total += sum(
                    int(rule.get("current_count", 0)) for rule in archive_rules
                )

        generated_at = datetime.now(timezone.utc).isoformat()
        return {
            "adaptation_queue": {
                "mode": "stage_two_adaptation_queue",
                "generated_at": generated_at,
                "total_candidate_count": adaptation_total,
                "sampled_record_count": cls._count_sampled_records(adaptation_sources),
                "sources": adaptation_sources,
            },
            "signal_bank": {
                "mode": "stage_two_signal_bank",
                "generated_at": generated_at,
                "total_candidate_count": signal_total,
                "sampled_record_count": cls._count_sampled_records(signal_sources),
                "sources": signal_sources,
            },
            "archive_manifest": {
                "mode": "stage_two_archive_manifest",
                "generated_at": generated_at,
                "total_candidate_count": archive_total,
                "sampled_record_count": cls._count_sampled_records(archive_sources),
                "sources": archive_sources,
            },
        }

    @staticmethod
    def render_markdown(artifacts: dict[str, dict[str, Any]]) -> str:
        lines = [
            "# Stage-Two Downstream Artifacts",
            "",
        ]
        for artifact_name in (
            "adaptation_queue",
            "signal_bank",
            "archive_manifest",
        ):
            artifact = artifacts[artifact_name]
            title = artifact_name.replace("_", " ").title()
            lines.extend(
                [
                    f"## {title}",
                    "",
                    f"- Generated at: {artifact.get('generated_at')}",
                    f"- Total candidate count: {artifact.get('total_candidate_count')}",
                    f"- Sampled record count: {artifact.get('sampled_record_count')}",
                    "",
                ]
            )
            for source in artifact.get("sources", []):
                lines.extend([f"### {source['source_name']}", ""])
                for rule in source.get("rules", []):
                    lines.extend(
                        [
                            f"- {rule['key_type']} `{rule['key']}` -> {rule['action']} ({rule['current_count']})",
                            f"  bucket: {rule['output_bucket']}",
                            f"  sampled records: {rule['sampled_record_count']}",
                            f"  rationale: {rule['rationale']}",
                        ]
                    )
                lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _collect_samples_by_source(
        review_payloads: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        samples_by_source: dict[str, list[dict[str, Any]]] = {}
        for payload in review_payloads:
            source_name = str(payload.get("source_name") or "unknown")
            result = payload.get("result", {})
            source_samples = samples_by_source.setdefault(source_name, [])
            for source_groups in result.get("parent_sources", {}).values():
                for group in source_groups:
                    source_samples.extend(group.get("samples", []))
        return samples_by_source

    @classmethod
    def _build_rule_payloads(
        cls,
        *,
        source_name: str,
        rules: list[dict[str, Any]],
        source_samples: list[dict[str, Any]],
        action: str,
    ) -> list[dict[str, Any]]:
        rule_payloads: list[dict[str, Any]] = []
        for rule in rules:
            if rule.get("action") != action:
                continue
            matching_samples = cls._match_samples_for_rule(rule, source_samples)
            rule_payloads.append(
                {
                    "source_name": source_name,
                    "key_type": rule.get("key_type"),
                    "key": rule.get("key"),
                    "action": action,
                    "output_bucket": rule.get("output_bucket"),
                    "adaptation_fit": rule.get("adaptation_fit"),
                    "rationale": rule.get("rationale"),
                    "current_count": int(rule.get("current_count", 0)),
                    "sampled_record_count": len(matching_samples),
                    "sampled_records": [
                        cls._serialize_sample(sample) for sample in matching_samples
                    ],
                    "label_summary": cls._build_label_summary(matching_samples),
                    "signal_summary": cls._build_signal_summary(matching_samples),
                }
            )
        return rule_payloads

    @staticmethod
    def _match_samples_for_rule(
        rule: dict[str, Any],
        samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        key_type = str(rule.get("key_type") or "")
        key = rule.get("key")
        if key_type == "route_subtype":
            return [sample for sample in samples if sample.get("route_subtype") == key]
        if key_type == "route_reason":
            return [
                sample
                for sample in samples
                if (sample.get("rejection_reason") or sample.get("route_reason")) == key
            ]
        return []

    @staticmethod
    def _serialize_sample(sample: dict[str, Any]) -> dict[str, Any]:
        derived_payload = sample.get("derived_payload") or {}
        return {
            "raw_record_id": sample.get("raw_record_id"),
            "route_outcome": sample.get("route_outcome"),
            "route_subtype": sample.get("route_subtype"),
            "route_reason": sample.get("route_reason"),
            "rejection_reason": sample.get("rejection_reason"),
            "extracted_label": sample.get("extracted_label"),
            "transformation_strength": sample.get("transformation_strength"),
            "similarity_score": sample.get("similarity_score"),
            "normalized_length": sample.get("normalized_length"),
            "normalized_preview": sample.get("normalized_preview"),
            "trace_summary": sample.get("trace_summary"),
            "derived_payload": derived_payload,
        }

    @staticmethod
    def _build_label_summary(samples: list[dict[str, Any]]) -> dict[str, int]:
        summary = Counter(
            str(sample.get("extracted_label") or "unknown") for sample in samples
        )
        return dict(summary)

    @staticmethod
    def _build_signal_summary(samples: list[dict[str, Any]]) -> dict[str, int]:
        ioc_enriched = 0
        phishing_relevant = 0
        promotion_eligible = 0
        for sample in samples:
            derived_payload = sample.get("derived_payload") or {}
            ioc_counts = derived_payload.get("ioc_counts", {})
            if sum(int(value) for value in ioc_counts.values()) > 0:
                ioc_enriched += 1
            if derived_payload.get("phishing_relevance") is True:
                phishing_relevant += 1
            if bool(derived_payload.get("promotion_eligible")):
                promotion_eligible += 1
        return {
            "ioc_enriched_records": ioc_enriched,
            "phishing_relevant_records": phishing_relevant,
            "promotion_eligible_records": promotion_eligible,
        }

    @staticmethod
    def _count_sampled_records(sources: list[dict[str, Any]]) -> int:
        return sum(
            int(rule.get("sampled_record_count", 0))
            for source in sources
            for rule in source.get("rules", [])
        )
