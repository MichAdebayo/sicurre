from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any


class GenerationStagingService:
    @classmethod
    def build_bundle(
        cls,
        *,
        generator_name: str,
        source_name: str,
        samples: list[dict[str, Any]],
        generated_at: str | None = None,
        parent_source: str | None = None,
        reference_selection_mode: str | None = None,
        input_artifact_uri: str | None = None,
        generated_artifact_uri: str | None = None,
        comparison_artifact_uri: str | None = None,
        monitor_artifact_uri: str | None = None,
        status: str = "completed",
    ) -> dict[str, Any]:
        resolved_generated_at = generated_at or datetime.now(UTC).isoformat()
        review_summary = Counter(
            str(sample.get("review_state") or "unknown") for sample in samples
        )

        run = {
            "generator_name": generator_name,
            "source_name": source_name,
            "parent_source": parent_source,
            "reference_selection_mode": reference_selection_mode,
            "input_artifact_uri": input_artifact_uri,
            "generated_artifact_uri": generated_artifact_uri,
            "comparison_artifact_uri": comparison_artifact_uri,
            "monitor_artifact_uri": monitor_artifact_uri,
            "status": status,
            "total_draft_count": len(samples),
            "usable_draft_count": review_summary.get("usable", 0),
            "needs_prompt_tuning_count": review_summary.get("needs_prompt_tuning", 0),
            "dropped_draft_count": review_summary.get("drop", 0),
            "created_at": resolved_generated_at,
            "started_at": resolved_generated_at,
            "finished_at": resolved_generated_at,
        }

        return {
            "mode": "no_write_generation_bundle",
            "generated_at": resolved_generated_at,
            "run": run,
            "sample_count": len(samples),
            "samples": samples,
        }

    @staticmethod
    def render_markdown(bundle: dict[str, Any]) -> str:
        run = dict(bundle.get("run") or {})
        lines = [
            "# No-Write Generation Bundle",
            "",
            f"- Generator: {run.get('generator_name')}",
            f"- Source: {run.get('source_name')}",
            f"- Parent source: {run.get('parent_source')}",
            f"- Status: {run.get('status')}",
            f"- Total drafts: {run.get('total_draft_count')}",
            f"- Usable drafts: {run.get('usable_draft_count')}",
            f"- Needs prompt tuning: {run.get('needs_prompt_tuning_count')}",
            f"- Dropped drafts: {run.get('dropped_draft_count')}",
            "",
        ]

        for sample in bundle.get("samples", []):
            lines.extend(
                [
                    f"## {sample.get('draft_id')}",
                    "",
                    f"- Variant index: {sample.get('variant_index')}",
                    f"- Target label: {sample.get('target_label')}",
                    f"- Review state: {sample.get('review_state')}",
                    f"- Primary theme: {sample.get('primary_theme')}",
                    f"- Review notes: {', '.join(sample.get('review_notes') or []) or 'none'}",
                    f"- Reference raw record: {sample.get('nearest_reference_raw_record_id')}",
                    f"- Similarity: {sample.get('nearest_similarity')}",
                    "",
                ]
            )

        return "\n".join(lines)
