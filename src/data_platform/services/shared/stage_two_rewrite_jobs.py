from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from data_platform.services.database.source_naming import canonical_database_source


class StageTwoRewriteJobService:
    @classmethod
    def build_jobs(cls, adaptation_queue: dict[str, Any]) -> dict[str, Any]:
        jobs: list[dict[str, Any]] = []

        for source in adaptation_queue.get("sources", []):
            source_name = str(source.get("source_name") or "unknown")
            for rule in source.get("rules", []):
                target_label = cls._resolve_target_label(rule)
                rewrite_mode = cls._resolve_rewrite_mode(rule)
                jobs.extend(
                    {
                        "job_id": cls._build_job_id(
                            source_name=source_name,
                            raw_record_id=str(sample.get("raw_record_id") or "unknown"),
                            rule_key=str(rule.get("key") or "unknown"),
                        ),
                        "source_name": source_name,
                        "rule_key": rule.get("key"),
                        "rewrite_mode": rewrite_mode,
                        "target_label": target_label,
                        "adaptation_fit": rule.get("adaptation_fit"),
                        "rationale": rule.get("rationale"),
                        "raw_record_id": sample.get("raw_record_id"),
                        "source_label": sample.get("extracted_label"),
                        "source_preview": sample.get("normalized_preview"),
                        "source_length": sample.get("normalized_length"),
                        "similarity_score": sample.get("similarity_score"),
                        "trace_summary": sample.get("trace_summary"),
                        "constraints": cls._build_constraints(
                            source_name=source_name,
                            rule_key=str(rule.get("key") or ""),
                            target_label=target_label,
                        ),
                        "prompt_hints": cls._build_prompt_hints(
                            source_name=source_name,
                            rule_key=str(rule.get("key") or ""),
                            sample=sample,
                        ),
                        "derived_payload": sample.get("derived_payload") or {},
                    }
                    for sample in rule.get("sampled_records", [])
                )

        return {
            "mode": "stage_two_rewrite_jobs",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "job_count": len(jobs),
            "jobs": jobs,
        }

    @staticmethod
    def render_markdown(job_payload: dict[str, Any]) -> str:
        lines = [
            "# Stage-Two Rewrite Jobs",
            "",
            f"- Generated at: {job_payload.get('generated_at')}",
            f"- Job count: {job_payload.get('job_count')}",
            "",
        ]

        for job in job_payload.get("jobs", []):
            lines.extend(
                [
                    f"## {job['job_id']}",
                    "",
                    f"- Source: {job['source_name']}",
                    f"- Rule key: {job['rule_key']}",
                    f"- Rewrite mode: {job['rewrite_mode']}",
                    f"- Target label: {job['target_label']}",
                    f"- Adaptation fit: {job['adaptation_fit']}",
                    f"- Raw record id: {job['raw_record_id']}",
                    f"- Constraints: {', '.join(job.get('constraints', []))}",
                    f"- Prompt hints: {', '.join(job.get('prompt_hints', []))}",
                    "",
                    job.get("source_preview") or "",
                    "",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _build_job_id(*, source_name: str, raw_record_id: str, rule_key: str) -> str:
        source_slug = source_name.replace("_", "-")
        return f"{source_slug}:{rule_key}:{raw_record_id}"

    @staticmethod
    def _resolve_target_label(rule: dict[str, Any]) -> str:
        key = str(rule.get("key") or "")
        if key == "promotional_spam":
            return "spam"
        if key in {"synthetic_lure_candidate", "phishing_lure_candidate"}:
            return "phishing"

        label_summary = rule.get("label_summary") or {}
        if label_summary:
            return max(label_summary.items(), key=lambda item: item[1])[0]
        return "unknown"

    @staticmethod
    def _resolve_rewrite_mode(rule: dict[str, Any]) -> str:
        key = str(rule.get("key") or "")
        if key == "instructional_legitimate":
            return "institutional_page_to_notification"
        if key == "awareness_or_report":
            return "awareness_page_to_warning_notification"
        if key == "promotional_spam":
            return "promotional_page_to_spam_message"
        if key in {"synthetic_lure_candidate", "phishing_lure_candidate"}:
            return "embedded_lure_to_phishing_email"
        return "repair_then_rewrite" if key.startswith("historical_") else "rewrite"

    @staticmethod
    def _build_constraints(
        *, source_name: str, rule_key: str, target_label: str
    ) -> list[str]:
        resolved_source_name = canonical_database_source(source_name)
        constraints = [
            "keep the text in French",
            "preserve the original intent and tone",
            "produce inbox-shaped subject/body style content",
        ]
        match target_label:
            case "legitimate":
                constraints.append("do not introduce phishing or spam cues")
            case "spam":
                constraints.append(
                    "preserve commercial pressure and promotional framing"
                )
            case "phishing":
                constraints.append(
                    "preserve deceptive urgency without adding IOCs verbatim"
                )
        if resolved_source_name == "database-historical":
            constraints.append(
                "repair encoding and formatting corruption before rewriting"
            )
        match rule_key:
            case "instructional_legitimate":
                constraints.append(
                    "convert page guidance into a concise customer notification"
                )
            case "awareness_or_report":
                constraints.append(
                    "shape the output as a defensive vigilance notification"
                )
            case "phishing_lure_candidate":
                constraints.append(
                    "extract the underlying lure from the scam-report context without copying the report scaffolding"
                )
        return constraints

    @staticmethod
    def _build_prompt_hints(
        *, source_name: str, rule_key: str, sample: dict[str, Any]
    ) -> list[str]:
        resolved_source_name = canonical_database_source(source_name)
        hints: list[str] = []
        derived_payload = sample.get("derived_payload") or {}
        marker_evidence = derived_payload.get("marker_evidence") or {}

        match resolved_source_name:
            case "common-crawl-bigdata":
                if int(marker_evidence.get("delivery_hits", 0)) > 0:
                    hints.append("retain service-notification delivery wording")
                if int(marker_evidence.get("promo_hits", 0)) > 0:
                    hints.append("retain offer and promotional vocabulary")
                if int(marker_evidence.get("awareness_hits", 0)) > 0:
                    hints.append("retain defensive fraud-awareness vocabulary")
                if int(marker_evidence.get("phishing_report_hits", 0)) > 0:
                    hints.append(
                        "extract the embedded scam pretext from the report wording"
                    )
                if int(marker_evidence.get("phishing_lure_hits", 0)) > 0:
                    hints.append("retain parcel, account, or delivery lure vocabulary")
            case "database-historical":
                hints.append("repair mojibake and strip residual HTML")

        match rule_key:
            case "synthetic_lure_candidate" | "phishing_lure_candidate":
                hints.append("shape the output as a realistic phishing email")
            case "awareness_or_report":
                hints.append("shape the output as a defensive vigilance reminder")
        return hints
