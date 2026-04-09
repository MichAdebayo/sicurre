import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[4]

GENERATED_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-generated-drafts.json"
CERTFR_REVIEW_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-full-review.json"
COMMON_CRAWL_REVIEW_DEFAULT = ROOT_DIR / "tasks/reviews/common-crawl-full-review.json"
HISTORICAL_REVIEW_DEFAULT = (
    ROOT_DIR / "tasks/reviews/database-historical-full-review.json"
)
OUTPUT_JSON_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-reference-comparison.json"
OUTPUT_MD_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-reference-comparison.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_review_samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for parent_source, source_entries in (
        payload.get("result", {}).get("parent_sources", {})
    ).items():
        for source_entry in source_entries:
            samples.extend(
                {
                    **sample,
                    "parent_source": parent_source,
                    "source_entry_name": source_entry.get("source"),
                    "source_entry_type": source_entry.get("source_type"),
                }
                for sample in source_entry.get("samples", [])
            )
    return samples


def normalize_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", text.lower()))


def similarity_scores(left: str, right: str) -> dict[str, float]:
    left_tokens = normalize_tokens(left)
    right_tokens = normalize_tokens(right)
    jaccard = 0.0
    if left_tokens or right_tokens:
        jaccard = len(left_tokens & right_tokens) / max(
            len(left_tokens | right_tokens), 1
        )
    sequence = SequenceMatcher(None, left[:600].lower(), right[:600].lower()).ratio()
    return {
        "jaccard": round(jaccard, 4),
        "sequence": round(sequence, 4),
        "combined": round((jaccard + sequence) / 2, 4),
    }


def build_reference_record(
    sample: dict[str, Any], *, reference_mode: str
) -> dict[str, Any]:
    text = str(
        sample.get("normalized_text")
        or sample.get("normalized_preview")
        or sample.get("raw_preview")
        or ""
    )
    return {
        "reference_mode": reference_mode,
        "raw_record_id": sample.get("raw_record_id"),
        "source_name": sample.get("source") or sample.get("source_entry_name"),
        "parent_source": sample.get("parent_source"),
        "route_outcome": sample.get("route_outcome"),
        "route_subtype": sample.get("route_subtype"),
        "label": sample.get("label") or sample.get("extracted_label"),
        "phishing_relevance": (sample.get("derived_payload") or {}).get(
            "phishing_relevance"
        ),
        "text": text,
        "text_length": len(text),
    }


def select_reference_samples(review_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    direct_write_ready: list[dict[str, Any]] = []
    specialized_fallback: list[dict[str, Any]] = []
    non_phishing_direct_write_count = 0

    for payload in review_payloads:
        for sample in iter_review_samples(payload):
            label = sample.get("label") or sample.get("extracted_label")
            route_outcome = sample.get("route_outcome")
            if route_outcome == "accepted" and label == "phishing":
                direct_write_ready.append(
                    build_reference_record(sample, reference_mode="direct_write_ready")
                )
            elif route_outcome == "accepted":
                non_phishing_direct_write_count += 1

            if (
                route_outcome == "specialized_processing"
                and label == "phishing"
                and (sample.get("derived_payload") or {}).get("phishing_relevance")
                is True
            ):
                specialized_fallback.append(
                    build_reference_record(
                        sample, reference_mode="specialized_fallback"
                    )
                )

    if direct_write_ready:
        return {
            "reference_selection_mode": "direct_write_ready",
            "references": direct_write_ready,
            "direct_write_ready_count": len(direct_write_ready),
            "fallback_count": len(specialized_fallback),
            "non_phishing_direct_write_count": non_phishing_direct_write_count,
        }

    return {
        "reference_selection_mode": "specialized_fallback",
        "references": specialized_fallback,
        "direct_write_ready_count": 0,
        "fallback_count": len(specialized_fallback),
        "non_phishing_direct_write_count": non_phishing_direct_write_count,
    }


def build_comparison_payload(
    generated_payload: dict[str, Any],
    review_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    reference_bundle = select_reference_samples(review_payloads)
    references = reference_bundle["references"]

    comparisons: list[dict[str, Any]] = []
    nearest_score_values: list[float] = []
    for draft in generated_payload.get("drafts", []):
        draft_text = str(draft.get("full_text") or draft.get("body") or "")
        best_reference: dict[str, Any] | None = None
        best_scores: dict[str, float] | None = None
        for reference in references:
            scores = similarity_scores(draft_text, str(reference.get("text") or ""))
            if best_scores is None or scores["combined"] > best_scores["combined"]:
                best_scores = scores
                best_reference = reference

        nearest_score_values.append((best_scores or {"combined": 0.0})["combined"])
        comparisons.append(
            {
                "draft_id": draft.get("draft_id"),
                "scenario_id": draft.get("scenario_id"),
                "theme": draft.get("primary_theme"),
                "review_state": draft.get("review_state"),
                "nearest_reference": {
                    "raw_record_id": (
                        best_reference.get("raw_record_id") if best_reference else None
                    ),
                    "source_name": (
                        best_reference.get("source_name") if best_reference else None
                    ),
                    "reference_mode": (
                        best_reference.get("reference_mode") if best_reference else None
                    ),
                    "label": best_reference.get("label") if best_reference else None,
                    "text_length": (
                        best_reference.get("text_length") if best_reference else None
                    ),
                },
                "similarity": best_scores
                or {"jaccard": 0.0, "sequence": 0.0, "combined": 0.0},
                "generated_quality_signals": draft.get("quality_signals", {}),
            }
        )

    return {
        "mode": "certfr_reference_comparison",
        "generated_draft_count": len(generated_payload.get("drafts", [])),
        "generated_review_summary": generated_payload.get("review_summary", {}),
        "generated_theme_summary": generated_payload.get("theme_summary", {}),
        "reference_selection_mode": reference_bundle["reference_selection_mode"],
        "direct_write_ready_count": reference_bundle["direct_write_ready_count"],
        "fallback_reference_count": reference_bundle["fallback_count"],
        "non_phishing_direct_write_count": reference_bundle[
            "non_phishing_direct_write_count"
        ],
        "average_nearest_similarity": round(
            sum(nearest_score_values) / max(len(nearest_score_values), 1),
            4,
        ),
        "reference_label_summary": dict(
            Counter(str(reference.get("label")) for reference in references)
        ),
        "comparisons": comparisons,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CERT-FR Reference Comparison",
        "",
        f"- Generated draft count: {payload['generated_draft_count']}",
        f"- Generated review summary: {payload['generated_review_summary']}",
        f"- Generated theme summary: {payload['generated_theme_summary']}",
        f"- Reference selection mode: {payload['reference_selection_mode']}",
        f"- Direct-write-ready phishing references: {payload['direct_write_ready_count']}",
        f"- Fallback CERT-FR phishing references: {payload['fallback_reference_count']}",
        f"- Non-phishing direct-write references observed: {payload['non_phishing_direct_write_count']}",
        f"- Average nearest similarity: {payload['average_nearest_similarity']}",
        f"- Reference label summary: {payload['reference_label_summary']}",
        "",
    ]

    for item in payload.get("comparisons", [])[:12]:
        lines.extend(
            [
                f"## {item['draft_id']}",
                "",
                f"- Theme: {item['theme']}",
                f"- Review state: {item['review_state']}",
                f"- Nearest reference raw record: {item['nearest_reference']['raw_record_id']}",
                f"- Nearest reference source: {item['nearest_reference']['source_name']}",
                f"- Reference mode: {item['nearest_reference']['reference_mode']}",
                f"- Similarity: {item['similarity']}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare CERT-FR generated drafts against the best available phishing references from review artifacts."
    )
    parser.add_argument("--generated", type=Path, default=GENERATED_DEFAULT)
    parser.add_argument("--certfr-review", type=Path, default=CERTFR_REVIEW_DEFAULT)
    parser.add_argument(
        "--common-crawl-review", type=Path, default=COMMON_CRAWL_REVIEW_DEFAULT
    )
    parser.add_argument(
        "--historical-review", type=Path, default=HISTORICAL_REVIEW_DEFAULT
    )
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON_DEFAULT)
    parser.add_argument("--output-md", type=Path, default=OUTPUT_MD_DEFAULT)
    args = parser.parse_args()

    generated_payload = read_json(args.generated)
    review_payloads = [
        read_json(args.certfr_review),
        read_json(args.common_crawl_review),
        read_json(args.historical_review),
    ]
    payload = build_comparison_payload(generated_payload, review_payloads)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.output_md.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
