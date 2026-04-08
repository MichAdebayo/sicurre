import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]

INPUT_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-generated-drafts.json"
OUTPUT_JSON_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-generation-monitor.json"
OUTPUT_MD_DEFAULT = ROOT_DIR / "tasks/reviews/certfr-generation-monitor.md"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_payload(generated_payload: dict[str, Any]) -> dict[str, Any]:
    drafts = generated_payload.get("drafts", [])
    total_drafts = len(drafts)
    unique_hash_count = len({str(draft.get("text_sha256")) for draft in drafts})
    duplicate_rate = round(1 - (unique_hash_count / max(total_drafts, 1)), 4)

    failure_note_summary = Counter()
    review_state_by_theme: dict[str, Counter[str]] = defaultdict(Counter)
    cta_position_by_theme: dict[str, Counter[str]] = defaultdict(Counter)
    sentence_template_usage: dict[str, Counter[str]] = {
        "opening": Counter(),
        "context": Counter(),
        "pressure": Counter(),
        "signature": Counter(),
    }
    cue_coverage_by_theme: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "draft_count": 0,
            "full_coverage_count": 0,
            "average_coverage_ratio": 0.0,
            "coverage_ratios": [],
        }
    )

    for draft in drafts:
        theme = str(draft.get("primary_theme") or "unknown")
        full_text = str(draft.get("full_text") or "").lower()
        lexical_cues = [str(cue).lower() for cue in draft.get("lexical_cues", [])]
        cue_hits = [cue for cue in lexical_cues if cue in full_text]
        coverage_ratio = round(len(cue_hits) / max(len(lexical_cues), 1), 4)

        cue_metrics = cue_coverage_by_theme[theme]
        cue_metrics["draft_count"] += 1
        cue_metrics["coverage_ratios"].append(coverage_ratio)
        if coverage_ratio >= 1.0:
            cue_metrics["full_coverage_count"] += 1

        review_state_by_theme[theme][str(draft.get("review_state"))] += 1
        cta_position_by_theme[theme][
            str((draft.get("quality_signals") or {}).get("cta_position"))
        ] += 1

        for note in draft.get("review_notes", []):
            failure_note_summary[str(note)] += 1

        quality_signals = draft.get("quality_signals") or {}
        sentence_template_usage["opening"][
            str(quality_signals.get("structure_opening"))
        ] += 1
        sentence_template_usage["context"][
            str(quality_signals.get("structure_context"))
        ] += 1
        sentence_template_usage["pressure"][
            str(quality_signals.get("structure_pressure"))
        ] += 1
        sentence_template_usage["signature"][
            str(quality_signals.get("structure_signature"))
        ] += 1

    for metrics in cue_coverage_by_theme.values():
        ratios = metrics.pop("coverage_ratios")
        metrics["average_coverage_ratio"] = round(
            sum(ratios) / max(len(ratios), 1),
            4,
        )

    return {
        "mode": "certfr_generation_monitor",
        "draft_count": total_drafts,
        "unique_full_text_count": unique_hash_count,
        "duplicate_rate": duplicate_rate,
        "review_summary": generated_payload.get("review_summary", {}),
        "failure_note_summary": dict(failure_note_summary),
        "cta_position_distribution": generated_payload.get("cta_position_summary", {}),
        "cta_position_by_theme": {
            key: dict(value) for key, value in cta_position_by_theme.items()
        },
        "cue_coverage_by_theme": dict(cue_coverage_by_theme),
        "review_state_by_theme": {
            key: dict(value) for key, value in review_state_by_theme.items()
        },
        "sentence_template_usage": {
            key: dict(counter.most_common(10))
            for key, counter in sentence_template_usage.items()
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CERT-FR Generation Monitor",
        "",
        f"- Draft count: {payload['draft_count']}",
        f"- Unique full texts: {payload['unique_full_text_count']}",
        f"- Duplicate rate: {payload['duplicate_rate']}",
        f"- Review summary: {payload['review_summary']}",
        f"- Failure note summary: {payload['failure_note_summary']}",
        f"- CTA position distribution: {payload['cta_position_distribution']}",
        "",
        "## Cue Coverage By Theme",
        "",
    ]

    for theme, metrics in payload.get("cue_coverage_by_theme", {}).items():
        lines.extend(
            [
                f"### {theme}",
                "",
                f"- Draft count: {metrics['draft_count']}",
                f"- Full coverage count: {metrics['full_coverage_count']}",
                f"- Average coverage ratio: {metrics['average_coverage_ratio']}",
                f"- Review states: {payload['review_state_by_theme'].get(theme)}",
                f"- CTA positions: {payload['cta_position_by_theme'].get(theme)}",
                "",
            ]
        )

    lines.extend(["## Sentence Template Usage", ""])
    for component, usage in payload.get("sentence_template_usage", {}).items():
        lines.extend([f"### {component}", ""])
        lines.extend(f"- {count}x: {sentence}" for sentence, count in usage.items())
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor duplicate risk and structural coverage for CERT-FR generated outputs."
    )
    parser.add_argument("--input", type=Path, default=INPUT_DEFAULT)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON_DEFAULT)
    parser.add_argument("--output-md", type=Path, default=OUTPUT_MD_DEFAULT)
    args = parser.parse_args()

    generated_payload = read_json(args.input)
    payload = build_payload(generated_payload)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.output_md.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
