import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from enum import StrEnum
from uuid import UUID
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_platform.cleaning.normalization import TextNormalizationService
from data_platform.services.database_source_naming import (
    DATABASE_PARENT_SOURCE,
    canonical_database_source,
)
from data_platform.services.certfr_stage_two import CertFRStageTwoService
from data_platform.services.common_crawl_content import CommonCrawlContentService
from data_platform.services.common_crawl_stage_two import CommonCrawlStageTwoService
from data_platform.services.historical_stage_two import HistoricalStageTwoService
from db.models.lineage import (
    DataRawRecord,
    DataNormalizedMessage,
    DataProcessingRun,
    DataSourceSystem,
    NormalizedLabel,
    RedactionStatus,
    IngestionStatus,
)

logger = logging.getLogger(__name__)

PHISHING_LABEL_VALUES = {
    "phishing",
    "phishing_related",
    "abuse_ch",
    "cert_gov_fr",
    "consumer_forum_fr",
    "phishing_feed",
    "reporting_gov_fr",
    "scam_reports_fr",
    "science_forum_fr",
    "security_news",
    "security_news_fr",
    "signal_spam_fr",
    "tech_forum_fr",
    "threat_intel_fr",
    "url_scanning",
}
SPAM_LABEL_VALUES = {
    "spam",
    "spam_like",
    "deal_aggregator_fr",
    "ecommerce_promo_fr",
    "retail_newsletter_fr",
}
LEGITIMATE_LABEL_VALUES = {
    "legitimate",
    "ham",
    "bank_fr",
    "gov_education_fr",
    "gov_economy_fr",
    "gov_employment_fr",
    "gov_interior_fr",
    "gov_legal_fr",
    "gov_services_fr",
    "health_authority_fr",
    "health_insurance_fr",
    "health_portal_fr",
    "postal_fr",
    "social_fr",
    "telecom_fr",
    "utility_fr",
}


class NormalizationLane(StrEnum):
    DIRECT_MESSAGE = "direct_message"
    PREPROCESS_MESSAGE = "preprocess_message"
    REVIEW_MESSAGE = "review_message"
    ADAPTATION_ONLY = "adaptation_only"
    URL_INTELLIGENCE = "url_intelligence"


@dataclass(frozen=True, slots=True)
class SourceNormalizationPolicy:
    lane: NormalizationLane
    normalize_messages: bool
    requires_french: bool = True
    reason: str | None = None


@dataclass
class ExtractedPayload:
    text: str | None
    label: NormalizedLabel | None
    contains_pii: bool = False
    redaction_status: RedactionStatus = RedactionStatus.NOT_REQUIRED
    rejection_reason: str | None = None
    route_outcome: str = "accepted"
    route_reason: str | None = None
    route_subtype: str | None = None
    derived_payload: dict[str, Any] | None = None
    trace_steps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DryRunSample:
    raw_record_id: str
    source_type: str
    source: str
    lane: str
    route_outcome: str
    route_subtype: str | None
    policy_reason: str | None
    route_reason: str | None
    extracted_label: str | None
    raw_preview: str
    normalized_preview: str | None
    contains_pii: bool
    redaction_status: str
    detected_language: str | None
    transformation_strength: str
    similarity_score: float | None
    raw_length: int
    normalized_length: int | None
    rejection_reason: str | None
    derived_payload: dict[str, Any] | None
    trace_summary: str


class WebCleaner:
    @staticmethod
    def clean_web_text(text: str, max_length: int = 2500) -> str:
        return CommonCrawlContentService.clean_web_text(text, max_length=max_length)


class NormalizationPipeline:
    PIPELINE_VERSION = "1.3.0"
    SOURCE_POLICIES: dict[str, SourceNormalizationPolicy] = {
        "database-historical": SourceNormalizationPolicy(
            lane=NormalizationLane.DIRECT_MESSAGE,
            normalize_messages=True,
        ),
        "kaggle_french_spamham": SourceNormalizationPolicy(
            lane=NormalizationLane.DIRECT_MESSAGE,
            normalize_messages=True,
        ),
        "kaggle_multilingual_spam": SourceNormalizationPolicy(
            lane=NormalizationLane.DIRECT_MESSAGE,
            normalize_messages=True,
        ),
        "sap-labs-blog": SourceNormalizationPolicy(
            lane=NormalizationLane.DIRECT_MESSAGE,
            normalize_messages=True,
        ),
        "common-crawl-bigdata": SourceNormalizationPolicy(
            lane=NormalizationLane.PREPROCESS_MESSAGE,
            normalize_messages=True,
        ),
        "cert-fr-cti": SourceNormalizationPolicy(
            lane=NormalizationLane.REVIEW_MESSAGE,
            normalize_messages=True,
            reason="cert_fr_message_candidate",
        ),
        "enron_spam": SourceNormalizationPolicy(
            lane=NormalizationLane.ADAPTATION_ONLY,
            normalize_messages=False,
            requires_french=False,
            reason="english_adaptation_source",
        ),
        "cybersectony_phishing_v2": SourceNormalizationPolicy(
            lane=NormalizationLane.ADAPTATION_ONLY,
            normalize_messages=False,
            requires_french=False,
            reason="english_adaptation_source",
        ),
        "data-en-hi-de-fr": SourceNormalizationPolicy(
            lane=NormalizationLane.ADAPTATION_ONLY,
            normalize_messages=False,
            requires_french=False,
            reason="mixed_language_adaptation_source",
        ),
        "zefang_phishing": SourceNormalizationPolicy(
            lane=NormalizationLane.ADAPTATION_ONLY,
            normalize_messages=False,
            requires_french=False,
            reason="english_adaptation_source",
        ),
        "phishtank-online-valid": SourceNormalizationPolicy(
            lane=NormalizationLane.URL_INTELLIGENCE,
            normalize_messages=False,
            requires_french=False,
            reason="url_intelligence_source",
        ),
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.normalization_service = TextNormalizationService()
        self.common_crawl_stage_two = CommonCrawlStageTwoService()
        self.certfr_stage_two = CertFRStageTwoService()
        self.historical_stage_two = HistoricalStageTwoService()

    @staticmethod
    def _preview_text(text: str | None, limit: int = 240) -> str:
        if not text:
            return ""
        compact = text.replace("\n", " ").strip()
        return compact if len(compact) <= limit else f"{compact[:limit]}..."

    @staticmethod
    def _resolve_source_name(
        source_system_id: UUID | None,
        sources: dict[UUID, str],
    ) -> str:
        if source_system_id is None:
            return "unknown"
        return sources.get(source_system_id, "unknown")

    @classmethod
    def get_source_policy(cls, source_name: str) -> SourceNormalizationPolicy | None:
        return cls.SOURCE_POLICIES.get(canonical_database_source(source_name))

    @staticmethod
    def _resolve_target_source_ids(
        sources: dict[str, str],
        source_system_name: str,
    ) -> set[str]:
        if source_system_name == DATABASE_PARENT_SOURCE:
            return {
                source_id
                for source_id, source_name in sources.items()
                if canonical_database_source(source_name) == DATABASE_PARENT_SOURCE
            }
        return {
            source_id
            for source_id, source_name in sources.items()
            if source_name == source_system_name
        }

    @classmethod
    def get_normalizable_source_names(cls) -> set[str]:
        return {
            source_name
            for source_name, policy in cls.SOURCE_POLICIES.items()
            if policy.normalize_messages
        }

    @staticmethod
    def _classify_transformation(
        raw_text: str,
        normalized_text: str | None,
    ) -> tuple[str, float | None]:
        if normalized_text is None:
            return "not_applicable", None

        compact_raw = re.sub(r"\s+", " ", raw_text).strip()
        compact_normalized = re.sub(r"\s+", " ", normalized_text).strip()
        if not compact_raw or not compact_normalized:
            return "unknown", None
        if compact_raw == compact_normalized:
            return "none", 1.0

        similarity = SequenceMatcher(None, compact_raw, compact_normalized).ratio()
        if similarity >= 0.97:
            return "minor", similarity
        if similarity >= 0.85:
            return "moderate", similarity
        return "major", similarity

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _join_subject_and_body(raw_content: dict[str, Any]) -> str:
        subject = str(raw_content.get("subject", "")).strip()
        body = str(raw_content.get("body", "")).strip()
        return f"Objet : {subject}\n\n{body}" if subject and body else body or subject

    @classmethod
    def _extract_review_text(cls, source_name: str, raw_content: dict[str, Any]) -> str:
        match canonical_database_source(source_name):
            case "sap-labs-blog" | "database-historical":
                review_text = cls._join_subject_and_body(raw_content)
            case "common-crawl-bigdata" | "cert-fr-cti":
                review_text = str(raw_content.get("text", "")).strip()
            case "kaggle_french_spamham" | "kaggle_multilingual_spam":
                review_text = str(raw_content.get("text", "")).strip()
            case "phishtank-online-valid":
                review_text = json.dumps(
                    {
                        key: raw_content.get(key)
                        for key in (
                            "url",
                            "domain",
                            "filter_reason",
                            "label",
                            "phish_detail_url",
                        )
                        if raw_content.get(key)
                    },
                    ensure_ascii=False,
                )
            case _:
                review_text = str(
                    raw_content.get("text")
                    or raw_content.get("body")
                    or raw_content.get("subject")
                    or ""
                ).strip()

        if review_text:
            return review_text
        return json.dumps(raw_content, ensure_ascii=False)

    def _build_dry_run_sample(
        self,
        *,
        raw_record_id: str,
        source_name: str,
        source_type: str,
        lane: str,
        route_outcome: str,
        route_subtype: str | None,
        policy_reason: str | None,
        route_reason: str | None,
        extracted_label: str | None,
        raw_text: str,
        normalized_text: str | None,
        contains_pii: bool,
        redaction_status: RedactionStatus,
        detected_language: str | None,
        rejection_reason: str | None,
        derived_payload: dict[str, Any] | None = None,
        trace_steps: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        transformation_strength, similarity_score = self._classify_transformation(
            raw_text,
            normalized_text,
        )
        return asdict(
            DryRunSample(
                raw_record_id=raw_record_id,
                source_type=source_type,
                source=source_name,
                lane=lane,
                route_outcome=route_outcome,
                route_subtype=route_subtype,
                policy_reason=policy_reason,
                route_reason=route_reason,
                extracted_label=extracted_label,
                raw_preview=self._preview_text(raw_text),
                normalized_preview=self._preview_text(normalized_text),
                contains_pii=contains_pii,
                redaction_status=redaction_status.value,
                detected_language=detected_language,
                transformation_strength=transformation_strength,
                similarity_score=similarity_score,
                raw_length=len(raw_text.strip()),
                normalized_length=(
                    len(normalized_text.strip()) if normalized_text else None
                ),
                rejection_reason=rejection_reason,
                derived_payload=derived_payload,
                trace_summary=" > ".join(trace_steps),
            )
        )

    @staticmethod
    def _strip_known_phrases(text: str, markers: tuple[str, ...]) -> str:
        cleaned_text = text
        for marker in markers:
            cleaned_text = re.sub(
                re.escape(marker),
                " ",
                cleaned_text,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", cleaned_text).strip()

    async def review_live_sources(
        self,
        samples_per_source: int = 10,
        source_system_name: str | None = None,
        source_type: str | None = None,
        route_outcome_filter: str | None = None,
        route_subtype_filter: str | None = None,
        max_kept_samples_per_source: int | None = None,
    ) -> dict[str, Any]:
        sources_query = select(DataSourceSystem).order_by(
            DataSourceSystem.source_type,
            DataSourceSystem.name,
        )
        sources_result = await self.session.execute(sources_query)
        source_systems = sources_result.scalars().all()

        grouped_sources: dict[str, list[dict[str, Any]]] = {}
        reviewed_source_count = 0
        total_sampled = 0

        for source in source_systems:
            if source_system_name:
                if source_system_name == DATABASE_PARENT_SOURCE:
                    if canonical_database_source(source.name) != DATABASE_PARENT_SOURCE:
                        continue
                elif source.name != source_system_name:
                    continue
            if source_type and source.source_type != source_type:
                continue

            policy = self.get_source_policy(source.name)
            reviewed_source_count += 1

            records_query = (
                select(DataRawRecord)
                .where(
                    DataRawRecord.source_system_id == source.id,
                    DataRawRecord.is_usable.is_(True),
                )
                .order_by(DataRawRecord.created_at.desc())
                .limit(samples_per_source)
            )
            if policy and policy.requires_french:
                records_query = records_query.where(
                    DataRawRecord.detected_language == "fr"
                )

            records_result = await self.session.execute(records_query)
            records = records_result.scalars().all()
            total_sampled += len(records)

            source_samples: list[dict[str, Any]] = []
            route_summary: Counter[str] = Counter()
            subtype_summary: Counter[str] = Counter()
            rejection_summary: Counter[str] = Counter()
            transformation_summary: Counter[str] = Counter()

            for record in records:
                raw_dict = json.loads(record.raw_content)
                raw_text = self._extract_review_text(source.name, raw_dict)
                lane = policy.lane.value if policy else "unmapped"

                if policy is None:
                    sample = self._build_dry_run_sample(
                        raw_record_id=str(record.id),
                        source_name=source.name,
                        source_type=source.source_type,
                        lane=lane,
                        route_outcome="unmapped_policy",
                        route_subtype=None,
                        policy_reason="missing_source_policy",
                        route_reason="missing_source_policy",
                        extracted_label=None,
                        raw_text=raw_text,
                        normalized_text=None,
                        contains_pii=False,
                        redaction_status=RedactionStatus.NOT_REQUIRED,
                        detected_language=record.detected_language,
                        rejection_reason="missing_source_policy",
                        derived_payload=None,
                        trace_steps=("missing_source_policy",),
                    )
                elif not policy.normalize_messages:
                    sample = self._build_dry_run_sample(
                        raw_record_id=str(record.id),
                        source_name=source.name,
                        source_type=source.source_type,
                        lane=lane,
                        route_outcome="routed_away",
                        route_subtype=None,
                        policy_reason=policy.reason,
                        route_reason=policy.reason,
                        extracted_label=None,
                        raw_text=raw_text,
                        normalized_text=None,
                        contains_pii=False,
                        redaction_status=RedactionStatus.NOT_REQUIRED,
                        detected_language=record.detected_language,
                        rejection_reason=policy.reason,
                        derived_payload=None,
                        trace_steps=("source_policy_routes_away",),
                    )
                else:
                    payload = self.extract_payload(source.name, raw_dict)
                    if payload.route_outcome == "accepted" and payload.label is None:
                        route_outcome = "missing_label"
                        rejection_reason = "missing_normalized_label"
                    else:
                        route_outcome = payload.route_outcome
                        rejection_reason = (
                            payload.rejection_reason or payload.route_reason
                        )

                    sample = self._build_dry_run_sample(
                        raw_record_id=str(record.id),
                        source_name=source.name,
                        source_type=source.source_type,
                        lane=lane,
                        route_outcome=route_outcome,
                        route_subtype=payload.route_subtype,
                        policy_reason=policy.reason,
                        route_reason=payload.route_reason,
                        extracted_label=(
                            payload.label.value if payload.label is not None else None
                        ),
                        raw_text=raw_text,
                        normalized_text=payload.text,
                        contains_pii=payload.contains_pii,
                        redaction_status=payload.redaction_status,
                        detected_language=record.detected_language,
                        rejection_reason=rejection_reason,
                        derived_payload=payload.derived_payload,
                        trace_steps=payload.trace_steps,
                    )

                route_summary[sample["route_outcome"]] += 1
                transformation_summary[sample["transformation_strength"]] += 1
                if sample["route_subtype"]:
                    subtype_summary[str(sample["route_subtype"])] += 1
                if sample["rejection_reason"]:
                    rejection_summary[sample["rejection_reason"]] += 1
                if (
                    route_outcome_filter
                    and sample["route_outcome"] != route_outcome_filter
                ):
                    continue
                if (
                    route_subtype_filter
                    and sample["route_subtype"] != route_subtype_filter
                ):
                    continue
                if (
                    max_kept_samples_per_source is not None
                    and len(source_samples) >= max_kept_samples_per_source
                ):
                    continue
                source_samples.append(sample)

            grouped_sources.setdefault(source.source_type, []).append(
                {
                    "source": source.name,
                    "source_type": source.source_type,
                    "lane": policy.lane.value if policy else "unmapped",
                    "normalize_messages": (
                        policy.normalize_messages if policy else False
                    ),
                    "policy_reason": (
                        policy.reason if policy else "missing_source_policy"
                    ),
                    "samples_requested": samples_per_source,
                    "route_filter": route_outcome_filter,
                    "route_subtype_filter": route_subtype_filter,
                    "samples_returned": len(source_samples),
                    "route_summary": dict(route_summary),
                    "subtype_summary": dict(subtype_summary),
                    "rejection_summary": dict(rejection_summary),
                    "transformation_summary": dict(transformation_summary),
                    "samples": source_samples,
                }
            )

        return {
            "status": "review success",
            "samples_per_source": samples_per_source,
            "reviewed_source_count": reviewed_source_count,
            "total_sampled": total_sampled,
            "parent_sources": grouped_sources,
        }

    @staticmethod
    def _map_binary_label(value: Any) -> NormalizedLabel | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return NormalizedLabel.PHISHING if value else NormalizedLabel.LEGITIMATE
        if isinstance(value, int):
            if value == 1:
                return NormalizedLabel.PHISHING
            if value == 0:
                return NormalizedLabel.LEGITIMATE
            return None

        normalized = str(value).strip().lower()
        if normalized in {"1"} | PHISHING_LABEL_VALUES:
            return NormalizedLabel.PHISHING
        if normalized in SPAM_LABEL_VALUES:
            return NormalizedLabel.SPAM
        if normalized in {"0"} | LEGITIMATE_LABEL_VALUES:
            return NormalizedLabel.LEGITIMATE
        return None

    def _normalize_payload_text(
        self,
        source_name: str,
        raw_content: dict[str, Any],
    ) -> tuple[str | None, bool, RedactionStatus, str | None]:
        match canonical_database_source(source_name):
            case "sap-labs-blog":
                candidate_text = self._join_subject_and_body(raw_content)
            case "common-crawl-bigdata":
                candidate_text = WebCleaner.clean_web_text(
                    str(raw_content.get("text", "")),
                    max_length=2500,
                )
            case "cert-fr-cti":
                candidate_text = WebCleaner.clean_web_text(
                    str(raw_content.get("text", "")),
                    max_length=3000,
                )
            case "database-historical":
                historical_body = str(raw_content.get("body") or "").strip()
                historical_subject = str(raw_content.get("subject") or "").strip()
                candidate_text = (
                    self._join_subject_and_body(
                        {"subject": historical_subject, "body": historical_body}
                    )
                    if historical_body
                    else str(raw_content.get("text") or "").strip()
                )
            case _:
                candidate_text = str(raw_content.get("text") or "").strip()

        artifact = self.normalization_service.normalize_text(candidate_text)
        if not artifact.is_usable:
            return (
                None,
                artifact.contains_redaction_tokens,
                RedactionStatus.NOT_REQUIRED,
                artifact.rejection_reason,
            )

        redaction_status = (
            RedactionStatus.REDACTED
            if artifact.contains_redaction_tokens
            else RedactionStatus.NOT_REQUIRED
        )
        return (
            artifact.cleaned_text,
            artifact.contains_redaction_tokens,
            redaction_status,
            None,
        )

    def extract_payload(
        self, source_name: str, raw_content: dict[str, Any]
    ) -> ExtractedPayload:
        resolved_source_name = canonical_database_source(source_name)
        policy = self.get_source_policy(source_name)
        if policy is None or not policy.normalize_messages:
            return ExtractedPayload(
                text=None,
                label=None,
                rejection_reason="source_not_normalized",
                route_outcome="routed_away",
                route_subtype=None,
                route_reason="source_not_normalized",
                derived_payload=None,
                trace_steps=("source_policy_routes_away",),
            )

        cleaned_text, contains_pii, redaction_status, normalization_rejection = (
            self._normalize_payload_text(
                source_name,
                raw_content,
            )
        )

        label: NormalizedLabel | None
        match resolved_source_name:
            case "sap-labs-blog":
                raw_label = str(raw_content.get("label", "")).lower()
                match raw_label:
                    case "phishing":
                        label = NormalizedLabel.PHISHING
                    case "legitimate":
                        label = NormalizedLabel.LEGITIMATE
                    case _:
                        label = None
            case "kaggle_french_spamham" | "kaggle_multilingual_spam":
                raw_label = str(raw_content.get("label", "")).lower()
                match raw_label:
                    case "spam":
                        label = NormalizedLabel.SPAM
                    case "ham":
                        label = NormalizedLabel.LEGITIMATE
                    case _:
                        label = None
            case "database-historical":
                label = self.historical_stage_two.map_label(raw_content)
            case "common-crawl-bigdata":
                label = self._map_binary_label(raw_content.get("label"))
                if label is None:
                    label = self._map_binary_label(raw_content.get("category"))
            case "cert-fr-cti":
                label = NormalizedLabel.PHISHING
            case _:
                label = None

        if cleaned_text is None:
            return ExtractedPayload(
                text=None,
                label=None,
                contains_pii=contains_pii,
                redaction_status=redaction_status,
                rejection_reason=normalization_rejection,
                route_outcome="rejected",
                route_subtype=None,
                route_reason=normalization_rejection,
                derived_payload=None,
                trace_steps=("shared_normalization_rejected",),
            )

        extraction_trace: tuple[str, ...] = ()
        route_trace: tuple[str, ...]
        derived_payload: dict[str, Any] | None = None
        extracted_text = cleaned_text
        match resolved_source_name:
            case "common-crawl-bigdata":
                stage_two_result = self.common_crawl_stage_two.review(
                    cleaned_text,
                    raw_content,
                )
                extracted_text = stage_two_result.extracted_text
                extraction_trace = stage_two_result.extraction_trace
                route_outcome = stage_two_result.route_outcome
                route_reason = stage_two_result.route_reason
                route_subtype = stage_two_result.route_subtype
                route_trace = stage_two_result.route_trace
                derived_payload = stage_two_result.derived_payload
            case "cert-fr-cti":
                stage_two_result = self.certfr_stage_two.review(
                    cleaned_text,
                    raw_content,
                )
                extracted_text = stage_two_result.extracted_text
                extraction_trace = stage_two_result.extraction_trace
                route_outcome = stage_two_result.route_outcome
                route_reason = stage_two_result.route_reason
                route_subtype = stage_two_result.route_subtype
                route_trace = stage_two_result.route_trace
                derived_payload = stage_two_result.derived_payload
            case "database-historical":
                stage_two_result = self.historical_stage_two.review(
                    cleaned_text,
                    raw_content,
                )
                extracted_text = stage_two_result.extracted_text
                extraction_trace = stage_two_result.extraction_trace
                route_outcome = stage_two_result.route_outcome
                route_reason = stage_two_result.route_reason
                route_subtype = None
                route_trace = stage_two_result.route_trace
                derived_payload = stage_two_result.derived_payload
            case _:
                extraction_trace = ()
                route_outcome, route_reason, trace_steps = (
                    "accepted",
                    None,
                    ("direct_message_gate_passed",),
                )
                route_subtype = None
                route_trace = trace_steps

        if resolved_source_name in {
            "common-crawl-bigdata",
            "cert-fr-cti",
            "database-historical",
        }:
            trace_steps = route_trace

        return ExtractedPayload(
            text=extracted_text,
            label=label,
            contains_pii=contains_pii,
            redaction_status=redaction_status,
            rejection_reason=(route_reason if route_outcome == "rejected" else None),
            route_outcome=route_outcome,
            route_reason=route_reason,
            route_subtype=route_subtype,
            derived_payload=derived_payload,
            trace_steps=extraction_trace + trace_steps,
        )

    async def run_batch(
        self,
        batch_size: int = 1000,
        source_system_name: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Normalize a batch of raw records directly into the normalized database schema."""
        logger.info(f"Starting Normalization Pipeline Phase 2 (Dry Run: {dry_run})")

        # 1. Fetch source systems mapping
        sources_query = select(DataSourceSystem)
        sources_result = await self.session.execute(sources_query)
        sources = {s.id: s.name for s in sources_result.scalars().all()}

        target_source_id = None
        target_source_ids: set[str] | None = None
        target_source_policy: SourceNormalizationPolicy | None = None
        if source_system_name:
            target_source_ids = self._resolve_target_source_ids(
                sources,
                source_system_name,
            )
            if target_source_ids:
                target_source_id = next(iter(target_source_ids))
                target_source_policy = self.get_source_policy(source_system_name)

            if not target_source_ids:
                logger.error(f"Source system {source_system_name} not found.")
                return {
                    "status": "error",
                    "message": f"Source {source_system_name} not found.",
                }

            if target_source_policy is None:
                return {
                    "status": "skipped",
                    "message": f"Source {source_system_name} has no normalization policy yet.",
                }

            if not target_source_policy.normalize_messages:
                return {
                    "status": "skipped",
                    "message": (
                        f"Source {source_system_name} is configured for "
                        f"{target_source_policy.lane.value} and is not normalized into messages."
                    ),
                }

        normalizable_source_ids = {
            source_id
            for source_id, source_name in sources.items()
            if (
                (policy := self.get_source_policy(source_name)) is not None
                and policy.normalize_messages
            )
        }

        # 2. Find Raw Records that have NOT been normalized AND are natively French
        query = (
            select(DataRawRecord)
            .where(
                ~DataRawRecord.normalized_messages.any(),  # NOT EXISTS relationship
                DataRawRecord.source_system_id.in_(normalizable_source_ids),
                DataRawRecord.detected_language == "fr",  # Tri-path isolation
                DataRawRecord.is_usable.is_(True),
            )
            .limit(batch_size)
        )
        if target_source_ids:
            query = query.where(DataRawRecord.source_system_id.in_(target_source_ids))

        result = await self.session.execute(query)
        records = result.scalars().all()

        if not records:
            logger.info("No pending French raw records found.")
            return {"normalized": 0, "skipped": 0, "dry_run": dry_run}

        logger.info(f"Found {len(records)} raw records to process.")

        if dry_run:
            samples = []
            rejections = []
            skipped_reasons: Counter[str] = Counter()
            for rec in records:
                source_name = self._resolve_source_name(rec.source_system_id, sources)
                raw_dict = json.loads(rec.raw_content)
                payload = self.extract_payload(source_name, raw_dict)
                source_policy = self.get_source_policy(source_name)
                lane = source_policy.lane.value if source_policy else "unknown"
                raw_preview = self._preview_text(
                    str(raw_dict.get("text") or self._join_subject_and_body(raw_dict))
                )
                if payload.text:
                    samples.append(
                        self._build_dry_run_sample(
                            raw_record_id=str(rec.id),
                            source_name=source_name,
                            source_type="filtered-dry-run",
                            lane=lane,
                            route_outcome=payload.route_outcome,
                            route_subtype=payload.route_subtype,
                            policy_reason=(
                                source_policy.reason if source_policy else None
                            ),
                            route_reason=payload.route_reason,
                            extracted_label=(
                                payload.label.value if payload.label else None
                            ),
                            raw_text=(
                                str(
                                    raw_dict.get("text")
                                    or self._join_subject_and_body(raw_dict)
                                )
                            ),
                            normalized_text=payload.text,
                            contains_pii=payload.contains_pii,
                            redaction_status=payload.redaction_status,
                            detected_language=rec.detected_language,
                            rejection_reason=payload.rejection_reason,
                            derived_payload=payload.derived_payload,
                            trace_steps=payload.trace_steps,
                        )
                    )
                else:
                    rejection_reason = (
                        payload.rejection_reason
                        or payload.route_reason
                        or "rejected_without_reason"
                    )
                    skipped_reasons[rejection_reason] += 1
                    rejections.append(
                        self._build_dry_run_sample(
                            raw_record_id=str(rec.id),
                            source_name=source_name,
                            source_type="filtered-dry-run",
                            lane=lane,
                            route_outcome=payload.route_outcome,
                            route_subtype=payload.route_subtype,
                            policy_reason=(
                                source_policy.reason if source_policy else None
                            ),
                            route_reason=payload.route_reason,
                            extracted_label=(
                                payload.label.value if payload.label else None
                            ),
                            raw_text=(
                                str(
                                    raw_dict.get("text")
                                    or self._join_subject_and_body(raw_dict)
                                )
                            ),
                            normalized_text=None,
                            contains_pii=payload.contains_pii,
                            redaction_status=payload.redaction_status,
                            detected_language=rec.detected_language,
                            rejection_reason=rejection_reason,
                            derived_payload=payload.derived_payload,
                            trace_steps=payload.trace_steps,
                        )
                    )
            return {
                "status": "dry-run success",
                "processed": len(records),
                "samples": samples,
                "rejections": rejections,
                "skipped_reasons": dict(skipped_reasons),
            }

        # Create Run Trace
        processing_run = DataProcessingRun(
            pipeline_version=self.PIPELINE_VERSION,
            started_at=self._utc_now(),
            status=IngestionStatus.RUNNING.value,
        )
        self.session.add(processing_run)
        await self.session.flush()

        existing_hashes_result = await self.session.execute(
            select(DataNormalizedMessage.text_sha256)
        )
        seen_hashes = set(existing_hashes_result.scalars().all())

        normalized_count = 0
        skipped_count = 0

        for rec in records:
            source_name = self._resolve_source_name(rec.source_system_id, sources)
            try:
                raw_dict = json.loads(rec.raw_content)
                payload = self.extract_payload(source_name, raw_dict)

                if (
                    payload.route_outcome != "accepted"
                    or not payload.text
                    or payload.label is None
                ):
                    skipped_count += 1
                    continue

                text_hash = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
                if text_hash in seen_hashes:
                    skipped_count += 1
                    continue

                norm_msg = DataNormalizedMessage(
                    raw_record_id=rec.id,
                    processing_run_id=processing_run.id,
                    normalized_text=payload.text,
                    text_sha256=text_hash,
                    language="fr",
                    current_label=payload.label.value,
                    contains_pii=payload.contains_pii,
                    redaction_status=payload.redaction_status.value,
                    text_length=len(payload.text),
                    normalized_at=self._utc_now(),
                )
                self.session.add(norm_msg)
                seen_hashes.add(text_hash)
                normalized_count += 1

            except Exception as e:
                logger.error(f"Error processing record {rec.id}: {e}")
                skipped_count += 1

        processing_run.status = IngestionStatus.COMPLETED.value
        processing_run.normalized_count = normalized_count
        processing_run.rejected_count = skipped_count
        processing_run.finished_at = self._utc_now()

        await self.session.commit()

        logger.info(
            f"Batch completed. Normalized: {normalized_count}, Skipped: {skipped_count}"
        )
        return {
            "normalized": normalized_count,
            "skipped": skipped_count,
            "run_id": str(processing_run.id),
        }
