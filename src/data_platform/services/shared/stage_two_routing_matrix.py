from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from data_platform.services.database.source_naming import canonical_database_source

RoutingAction = Literal[
    "promote",
    "adapt",
    "extract_signals_only",
    "archive",
]
RoutingKeyType = Literal["route_subtype", "route_reason"]


@dataclass(frozen=True, slots=True)
class StageTwoRoutingRule:
    source_name: str
    key_type: RoutingKeyType
    key: str
    action: RoutingAction
    output_bucket: str
    adaptation_fit: str
    rationale: str


class StageTwoRoutingMatrixService:
    RULES: tuple[StageTwoRoutingRule, ...] = (
        StageTwoRoutingRule(
            source_name="common-crawl-bigdata",
            key_type="route_subtype",
            key="transactional_legitimate",
            action="promote",
            output_bucket="promotion_queue",
            adaptation_fit="none",
            rationale=(
                "Already close to inbox-shaped legitimate notifications and suitable "
                "for reviewed promotion."
            ),
        ),
        StageTwoRoutingRule(
            source_name="common-crawl-bigdata",
            key_type="route_subtype",
            key="instructional_legitimate",
            action="adapt",
            output_bucket="adaptation_queue",
            adaptation_fit="high",
            rationale=(
                "Carries strong French institutional wording but still needs rewriting "
                "from page form into message form."
            ),
        ),
        StageTwoRoutingRule(
            source_name="common-crawl-bigdata",
            key_type="route_subtype",
            key="promotional_spam",
            action="adapt",
            output_bucket="adaptation_queue",
            adaptation_fit="high",
            rationale=(
                "Useful source of real French promotional pressure language for spam "
                "adaptation, but not safe for direct writes."
            ),
        ),
        StageTwoRoutingRule(
            source_name="common-crawl-bigdata",
            key_type="route_subtype",
            key="awareness_or_report",
            action="adapt",
            output_bucket="adaptation_queue",
            adaptation_fit="medium",
            rationale=(
                "Fraud-awareness pages carry useful defensive wording that can be "
                "rewritten into legitimate warning and security-notification messages."
            ),
        ),
        StageTwoRoutingRule(
            source_name="common-crawl-bigdata",
            key_type="route_subtype",
            key="phishing_lure_candidate",
            action="adapt",
            output_bucket="adaptation_queue",
            adaptation_fit="high",
            rationale=(
                "Scam-report pages expose recurring French lure wording and delivery/account "
                "pretexts that can be rewritten into phishing examples after review."
            ),
        ),
        StageTwoRoutingRule(
            source_name="common-crawl-bigdata",
            key_type="route_subtype",
            key="navigation_heavy_holdout",
            action="archive",
            output_bucket="dead_holdout_archive",
            adaptation_fit="none",
            rationale=(
                "Dominated by page chrome and low message density, so additional effort "
                "has poor return."
            ),
        ),
        StageTwoRoutingRule(
            source_name="common-crawl-bigdata",
            key_type="route_subtype",
            key="no_window_holdout",
            action="archive",
            output_bucket="dead_holdout_archive",
            adaptation_fit="none",
            rationale=(
                "No stable message window was found, so this stays out of active "
                "processing until chunk extraction materially improves recall."
            ),
        ),
        StageTwoRoutingRule(
            source_name="cert-fr-cti",
            key_type="route_subtype",
            key="threat_intel",
            action="extract_signals_only",
            output_bucket="signal_bank",
            adaptation_fit="medium",
            rationale=(
                "Extract campaign themes, targets, lures, and IOCs first; those signals "
                "can later seed phishing adaptation without writing the report text itself."
            ),
        ),
        StageTwoRoutingRule(
            source_name="cert-fr-cti",
            key_type="route_subtype",
            key="synthetic_lure_candidate",
            action="adapt",
            output_bucket="adaptation_queue",
            adaptation_fit="high",
            rationale=(
                "Already message-shaped enough to rewrite into realistic phishing examples "
                "after review."
            ),
        ),
        StageTwoRoutingRule(
            source_name="cert-fr-cti",
            key_type="route_subtype",
            key="procedural_notification",
            action="extract_signals_only",
            output_bucket="signal_bank",
            adaptation_fit="low",
            rationale=(
                "Useful as security-notification reference phrasing, but not a priority "
                "adaptation source."
            ),
        ),
        StageTwoRoutingRule(
            source_name="cert-fr-cti",
            key_type="route_subtype",
            key="irrecoverable_holdout",
            action="archive",
            output_bucket="dead_holdout_archive",
            adaptation_fit="none",
            rationale=(
                "Does not contain a recoverable embedded message or enough scenario value "
                "to justify continued processing."
            ),
        ),
        StageTwoRoutingRule(
            source_name="database-historical",
            key_type="route_reason",
            key="historical_repair_needed",
            action="adapt",
            output_bucket="adaptation_queue",
            adaptation_fit="medium",
            rationale=(
                "The semantics may still be salvageable after repair, so these belong in a "
                "repair-and-rewrite lane rather than immediate discard."
            ),
        ),
        StageTwoRoutingRule(
            source_name="database-historical",
            key_type="route_reason",
            key="historical_html_repair_required",
            action="adapt",
            output_bucket="adaptation_queue",
            adaptation_fit="medium",
            rationale=(
                "Residual markup is a formatting problem more than a semantic one, so a "
                "repair pass can still recover useful message content."
            ),
        ),
        StageTwoRoutingRule(
            source_name="database-historical",
            key_type="route_reason",
            key="historical_language_recheck_required",
            action="archive",
            output_bucket="dead_holdout_archive",
            adaptation_fit="none",
            rationale=(
                "Mostly non-French or cross-language spillover, so it weakens the French "
                "corpus more than it helps."
            ),
        ),
        StageTwoRoutingRule(
            source_name="database-historical",
            key_type="route_reason",
            key="historical_content_too_thin",
            action="archive",
            output_bucket="dead_holdout_archive",
            adaptation_fit="none",
            rationale=(
                "Too little message substance remains after cleanup to justify adaptation "
                "or signal extraction."
            ),
        ),
    )

    @classmethod
    def build_matrix(cls, review_payloads: list[dict[str, Any]]) -> dict[str, Any]:
        summaries_by_source = cls._build_source_summaries(review_payloads)
        source_rows: dict[str, list[dict[str, Any]]] = {}

        for rule in cls.RULES:
            source_summary = summaries_by_source.get(rule.source_name, {})
            key_summary = source_summary.get(f"{rule.key_type}_summary", {})
            current_count = int(key_summary.get(rule.key, 0))
            source_rows.setdefault(rule.source_name, []).append(
                {
                    **asdict(rule),
                    "current_count": current_count,
                }
            )

        sources: list[dict[str, Any]] = []
        for source_name, rows in source_rows.items():
            summary = summaries_by_source.get(source_name, {})
            action_summary = Counter(row["action"] for row in rows)
            sources.append(
                {
                    "source_name": source_name,
                    "route_summary": summary.get("route_summary", {}),
                    "subtype_summary": summary.get("route_subtype_summary", {}),
                    "rejection_summary": summary.get("route_reason_summary", {}),
                    "action_summary": dict(action_summary),
                    "rows": rows,
                }
            )

        return {
            "mode": "stage_two_routing_matrix",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
        }

    @staticmethod
    def render_markdown(matrix: dict[str, Any]) -> str:
        lines = [
            "# Stage-Two Routing Matrix",
            "",
            f"- Generated at: {matrix.get('generated_at')}",
            "- Scope: non-promotable and second-pass review paths",
            "- Actions: `promote`, `adapt`, `extract_signals_only`, `archive`",
            "",
        ]

        for source in matrix.get("sources", []):
            lines.extend(
                [
                    f"## {source['source_name']}",
                    "",
                    f"- Route summary: {source.get('route_summary', {})}",
                    f"- Subtype summary: {source.get('subtype_summary', {})}",
                    f"- Rejection summary: {source.get('rejection_summary', {})}",
                    "",
                    "| key type | key | action | output bucket | current count | adaptation fit | rationale |",
                    "| --- | --- | --- | --- | ---: | --- | --- |",
                ]
            )
            for row in source.get("rows", []):
                lines.append(
                    "| "
                    f"{row['key_type']} | {row['key']} | {row['action']} | "
                    f"{row['output_bucket']} | {row['current_count']} | "
                    f"{row['adaptation_fit']} | {row['rationale']} |"
                )
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _build_source_summaries(
        review_payloads: list[dict[str, Any]],
    ) -> dict[str, dict[str, dict[str, int]]]:
        summaries: dict[str, dict[str, Counter[str]]] = {}

        for payload in review_payloads:
            source_name = canonical_database_source(
                str(payload.get("source_name") or "unknown")
            )
            source_entry = summaries.setdefault(
                source_name,
                {
                    "route_summary": Counter(),
                    "route_subtype_summary": Counter(),
                    "route_reason_summary": Counter(),
                },
            )
            result = payload.get("result", {})
            for source_groups in result.get("parent_sources", {}).values():
                for group in source_groups:
                    source_entry["route_summary"].update(group.get("route_summary", {}))
                    source_entry["route_subtype_summary"].update(
                        group.get("subtype_summary", {})
                    )
                    source_entry["route_reason_summary"].update(
                        group.get("rejection_summary", {})
                    )

        return {
            source_name: {
                summary_name: dict(summary_counter)
                for summary_name, summary_counter in source_summary.items()
            }
            for source_name, source_summary in summaries.items()
        }
