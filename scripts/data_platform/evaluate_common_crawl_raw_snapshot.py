from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.normalization_pipeline import NormalizationPipeline
from data_platform.services.stage_two_action_artifacts import (
    StageTwoActionArtifactsService,
)
from data_platform.services.stage_two_reviewed_export import (
    StageTwoReviewedExportService,
)
from data_platform.services.stage_two_rewrite_drafts import StageTwoRewriteDraftService
from data_platform.services.stage_two_rewrite_jobs import StageTwoRewriteJobService
from data_platform.services.structured_review_artifact import (
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = (
    ROOT_DIR / "data/raw/bigdata/common_crawl/common_crawl_fr_usable_1220_20260406.csv"
)
DEFAULT_OUTPUT_JSON = (
    ROOT_DIR / "tasks/reviews/common-crawl-raw-three-class-evaluation.json"
)
DEFAULT_OUTPUT_MD = (
    ROOT_DIR / "tasks/reviews/common-crawl-raw-three-class-evaluation.md"
)
DEFAULT_DRAFTS_JSON = (
    ROOT_DIR / "tasks/reviews/common-crawl-raw-three-class-drafts.json"
)
DEFAULT_EXPORT_JSON = (
    ROOT_DIR / "tasks/reviews/common-crawl-raw-three-class-export.json"
)
DEFAULT_EXPORT_CSV = ROOT_DIR / "tasks/reviews/common-crawl-raw-three-class-export.csv"
DEFAULT_MATRIX = ROOT_DIR / "tasks/reviews/stage-two-routing-matrix.json"

LEGITIMATE_SUBTYPES = {
    "transactional_legitimate",
    "instructional_legitimate",
    "awareness_or_report",
}
SPAM_SUBTYPES = {"promotional_spam"}
PHISHING_SUBTYPES = {"phishing_lure_candidate"}
ADAPTABLE_SUBTYPES = {
    "instructional_legitimate",
    "awareness_or_report",
    "promotional_spam",
    "phishing_lure_candidate",
}


def _target_from_subtype(route_subtype: str | None) -> str:
    if route_subtype in LEGITIMATE_SUBTYPES:
        return "legitimate"
    if route_subtype in SPAM_SUBTYPES:
        return "spam"
    return "phishing" if route_subtype in PHISHING_SUBTYPES else "holdout"


def _normalize_label(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value.value if hasattr(value, "value") else value)


def _load_rule_metadata(matrix_path: Path) -> dict[str, dict[str, Any]]:
    matrix = StructuredReviewArtifactService.read_json(matrix_path)
    for source in matrix.get("sources", []):
        if source.get("source_name") != "common-crawl-bigdata":
            continue
        return {
            str(row.get("key")): row
            for row in source.get("rows", [])
            if row.get("action") == "adapt"
        }
    return {}


def _build_sample(
    *,
    row_index: int,
    row: dict[str, str],
    payload: Any,
) -> dict[str, Any]:
    text = payload.text or ""
    route_target = _target_from_subtype(payload.route_subtype)
    extracted_label = (
        route_target if route_target != "holdout" else _normalize_label(payload.label)
    )
    return {
        "raw_record_id": f"common-crawl-raw:{row_index}",
        "route_outcome": payload.route_outcome,
        "route_subtype": payload.route_subtype,
        "route_reason": payload.route_reason,
        "rejection_reason": payload.rejection_reason,
        "extracted_label": extracted_label,
        "transformation_strength": "major",
        "similarity_score": 0.0,
        "normalized_length": len(text.strip()) if text else 0,
        "normalized_preview": text,
        "trace_summary": " > ".join(payload.trace_steps),
        "derived_payload": payload.derived_payload or {},
        "source_label": row.get("label") or "unknown",
        "source_category": row.get("category") or "unknown",
        "source_url": row.get("url") or "",
    }


def _build_adaptation_queue(
    *,
    samples_by_subtype: dict[str, list[dict[str, Any]]],
    rule_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for subtype in (
        "instructional_legitimate",
        "awareness_or_report",
        "promotional_spam",
        "phishing_lure_candidate",
    ):
        matching_samples = samples_by_subtype.get(subtype, [])
        if not matching_samples:
            continue
        deduped = StageTwoActionArtifactsService._deduplicate_adaptation_samples(
            matching_samples
        )
        metadata = rule_metadata.get(subtype, {})
        label_summary = Counter(
            str(sample.get("extracted_label") or "unknown") for sample in deduped
        )
        rules.append(
            {
                "source_name": "common-crawl-bigdata",
                "key_type": "route_subtype",
                "key": subtype,
                "action": "adapt",
                "output_bucket": metadata.get("output_bucket", "adaptation_queue"),
                "adaptation_fit": metadata.get("adaptation_fit", "high"),
                "rationale": metadata.get("rationale", "raw snapshot evaluation"),
                "current_count": len(matching_samples),
                "sampled_record_count": len(deduped),
                "sampled_records": deduped,
                "label_summary": dict(label_summary),
            }
        )

    return {
        "mode": "common_crawl_raw_three_class_adaptation_queue",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_candidate_count": sum(rule["current_count"] for rule in rules),
        "sampled_record_count": sum(rule["sampled_record_count"] for rule in rules),
        "sources": [{"source_name": "common-crawl-bigdata", "rules": rules}],
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Common Crawl Raw Three-Class Evaluation",
        "",
        f"- Generated at: {summary['generated_at']}",
        f"- Input snapshot: {summary['input_snapshot']}",
        f"- Total raw rows: {summary['raw_total']}",
        f"- Raw category summary: {summary['raw_category_summary']}",
        f"- Raw target partition: {summary['raw_target_partition']}",
        f"- High-fidelity partition: {summary['high_fidelity_partition']}",
        "",
        "## Raw Route Subtypes",
        "",
    ]
    lines.extend(
        f"- {key}: {value}"
        for key, value in summary["raw_route_subtype_summary"].items()
    )
    lines.extend(
        [
            "",
            "## Adaptation Queue",
            "",
        ]
    )
    lines.extend(
        f"- {key}: {value}" for key, value in summary["adaptation_rule_summary"].items()
    )
    lines.extend(
        [
            "",
            "## Draft States",
            "",
        ]
    )
    lines.extend(
        f"- {rule_key}: {counts}"
        for rule_key, counts in summary["draft_rule_state"].items()
    )
    lines.extend(
        [
            "",
            "## Exported High-Fidelity Candidates",
            "",
            f"- Exported count: {summary['export_count']}",
            f"- Export label summary: {summary['export_label_summary']}",
            f"- Export rule summary: {summary['export_rule_summary']}",
            "",
            "## Source Family Partition",
            "",
        ]
    )
    lines.extend(
        f"- {label}: {partition}"
        for label, partition in summary["source_label_partition"].items()
    )
    lines.extend(
        [
            "",
            "## Sample Export Subjects",
            "",
        ]
    )
    lines.extend(f"- {subject}" for subject in summary["sample_export_subjects"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the raw Common Crawl snapshot across legitimate, spam, and phishing lanes."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--drafts-json", type=Path, default=DEFAULT_DRAFTS_JSON)
    parser.add_argument("--export-json", type=Path, default=DEFAULT_EXPORT_JSON)
    parser.add_argument("--export-csv", type=Path, default=DEFAULT_EXPORT_CSV)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    args = parser.parse_args()

    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]
    rule_metadata = _load_rule_metadata(args.matrix)

    raw_total = 0
    raw_category_summary: Counter[str] = Counter()
    raw_route_subtype_summary: Counter[str] = Counter()
    raw_target_partition: Counter[str] = Counter()
    source_label_partition: dict[str, Counter[str]] = defaultdict(Counter)
    direct_legitimate_count = 0
    samples_by_subtype: dict[str, list[dict[str, Any]]] = defaultdict(list)

    with args.input.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=1):
            raw_total += 1
            raw_category_summary.update([row.get("category") or "unknown"])
            payload = pipeline.extract_payload(
                "common-crawl-bigdata",
                {
                    "text": row.get("text", ""),
                    "label": row.get("label"),
                    "category": row.get("category"),
                    "query": row.get("query"),
                    "query_label": row.get("label"),
                    "url": row.get("url"),
                },
            )
            route_subtype = payload.route_subtype or "none"
            target = _target_from_subtype(payload.route_subtype)
            raw_route_subtype_summary.update([route_subtype])
            raw_target_partition.update([target])
            source_label_partition[row.get("label") or "unknown"].update([target])
            if payload.route_subtype == "transactional_legitimate":
                direct_legitimate_count += 1

            if payload.route_subtype in ADAPTABLE_SUBTYPES:
                samples_by_subtype[payload.route_subtype].append(
                    _build_sample(row_index=row_index, row=row, payload=payload)
                )

    adaptation_queue = _build_adaptation_queue(
        samples_by_subtype=samples_by_subtype,
        rule_metadata=rule_metadata,
    )
    rewrite_jobs = StageTwoRewriteJobService.build_jobs(adaptation_queue)
    rewrite_drafts = StageTwoRewriteDraftService.build_drafts(rewrite_jobs)
    export_payload = StageTwoReviewedExportService().build_export(rewrite_drafts)

    args.drafts_json.parent.mkdir(parents=True, exist_ok=True)
    StructuredReviewArtifactService.write_json(args.drafts_json, rewrite_drafts)
    StructuredReviewArtifactService.write_json(args.export_json, export_payload)
    StageTwoReviewedExportService.write_csv(export_payload, args.export_csv)

    draft_rule_state: dict[str, dict[str, int]] = defaultdict(dict)
    for rule_key in ADAPTABLE_SUBTYPES:
        if counter := Counter(
            draft.get("review_state")
            for draft in rewrite_drafts.get("drafts", [])
            if draft.get("source_name") == "common-crawl-bigdata"
            and draft.get("rule_key") == rule_key
        ):
            draft_rule_state[rule_key] = dict(counter)

    export_label_summary = Counter(
        candidate.get("target_label")
        for candidate in export_payload.get("candidates", [])
    )
    export_rule_summary = Counter(
        candidate.get("rule_key") for candidate in export_payload.get("candidates", [])
    )
    high_fidelity_partition = {
        "legitimate": direct_legitimate_count
        + export_label_summary.get("legitimate", 0),
        "spam": export_label_summary.get("spam", 0),
        "phishing": export_label_summary.get("phishing", 0),
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_snapshot": str(args.input.relative_to(ROOT_DIR)),
        "raw_total": raw_total,
        "raw_category_summary": dict(raw_category_summary),
        "raw_route_subtype_summary": dict(raw_route_subtype_summary),
        "raw_target_partition": dict(raw_target_partition),
        "adaptation_rule_summary": {
            rule["key"]: {
                "current_count": rule["current_count"],
                "sampled_record_count": rule["sampled_record_count"],
            }
            for source in adaptation_queue.get("sources", [])
            for rule in source.get("rules", [])
        },
        "draft_rule_state": draft_rule_state,
        "export_count": export_payload.get("exported_candidate_count", 0),
        "export_label_summary": dict(export_label_summary),
        "export_rule_summary": dict(export_rule_summary),
        "high_fidelity_partition": high_fidelity_partition,
        "source_label_partition": {
            label: dict(counter) for label, counter in source_label_partition.items()
        },
        "sample_export_subjects": [
            str(candidate.get("normalized_text") or "").split("\n", 1)[0]
            for candidate in export_payload.get("candidates", [])[:12]
        ],
    }

    StructuredReviewArtifactService.write_json(args.output_json, summary)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(_render_markdown(summary), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
