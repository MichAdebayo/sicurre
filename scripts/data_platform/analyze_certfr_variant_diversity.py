import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.services.certfr_generated_drafts import (  # noqa: E402
    CertFRGeneratedDraftService,
)
from data_platform.services.structured_review_artifact import (  # noqa: E402
    StructuredReviewArtifactService,
)

DEFAULT_INPUT = ROOT_DIR / "tasks/reviews/certfr-synthesis-inputs.json"
DEFAULT_JSON = ROOT_DIR / "tasks/reviews/certfr-variant-diversity.json"
DEFAULT_MD = ROOT_DIR / "tasks/reviews/certfr-variant-diversity.md"


def render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# CERT-FR Variant Diversity Audit",
        "",
        f"- Variants per scenario: {payload['variants_per_scenario']}",
        f"- Scenario count: {payload['scenario_count']}",
        f"- Total generated drafts: {payload['total_drafts']}",
        f"- Unique full texts: {payload['unique_full_text_count']}",
        f"- Duplicate full texts: {payload['duplicate_full_text_count']}",
        f"- Unique ratio: {payload['unique_ratio']}",
        f"- Review summary: {payload['review_summary']}",
        "",
        "## Scenario Summary",
        "",
    ]

    for item in payload["scenario_summaries"]:
        lines.extend(
            [
                f"### {item['scenario_id']}",
                "",
                f"- Unique full texts: {item['unique_full_text_count']} / {item['draft_count']}",
                f"- Review summary: {item['review_summary']}",
                f"- CTA positions: {item['cta_position_summary']}",
                "",
            ]
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate scaled CERT-FR generation and measure duplicate risk across variants."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--variants-per-scenario", type=int, default=56)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    synthesis_payload = StructuredReviewArtifactService.read_json(args.input)
    expanded_scenarios: list[dict[str, object]] = []
    for scenario in synthesis_payload.get("scenarios", []):
        expanded_scenarios.extend(
            {**scenario, "variant_index": variant_index}
            for variant_index in range(args.variants_per_scenario)
        )

    drafts_payload = CertFRGeneratedDraftService.build_drafts(
        {"scenarios": expanded_scenarios}
    )
    drafts = drafts_payload["drafts"]

    scenario_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for draft in drafts:
        scenario_groups[str(draft["scenario_id"])].append(draft)

    scenario_summaries = []
    for scenario_id, items in sorted(scenario_groups.items()):
        unique_full_text_count = len({str(item["text_sha256"]) for item in items})
        scenario_summaries.append(
            {
                "scenario_id": scenario_id,
                "draft_count": len(items),
                "unique_full_text_count": unique_full_text_count,
                "review_summary": dict(
                    Counter(str(item["review_state"]) for item in items)
                ),
                "cta_position_summary": dict(
                    Counter(
                        str(item.get("quality_signals", {}).get("cta_position"))
                        for item in items
                    )
                ),
            }
        )

    unique_full_text_count = len({str(draft["text_sha256"]) for draft in drafts})
    payload = {
        "mode": "certfr_variant_diversity_audit",
        "variants_per_scenario": args.variants_per_scenario,
        "scenario_count": len(synthesis_payload.get("scenarios", [])),
        "total_drafts": len(drafts),
        "unique_full_text_count": unique_full_text_count,
        "duplicate_full_text_count": len(drafts) - unique_full_text_count,
        "unique_ratio": round(unique_full_text_count / max(len(drafts), 1), 4),
        "review_summary": dict(Counter(str(draft["review_state"]) for draft in drafts)),
        "scenario_summaries": scenario_summaries,
    }

    StructuredReviewArtifactService.write_json(args.output_json, payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
