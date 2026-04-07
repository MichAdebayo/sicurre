import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_platform.cleaning.normalization import TextNormalizationService
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


@dataclass
class ExtractedPayload:
    text: str | None
    label: NormalizedLabel | None
    contains_pii: bool = False
    redaction_status: RedactionStatus = RedactionStatus.NOT_REQUIRED


class WebCleaner:
    @staticmethod
    def clean_web_text(text: str, max_length: int = 2500) -> str:
        """Strip HTML menus, repetitive UI artifacts, and truncate."""
        # Simple heuristic to remove excessive newlines and tab artifacts from scrapers
        clean_text = re.sub(r"(\n\s*){3,}", "\n\n", text)
        clean_text = re.sub(
            r"(?i)(accepter les cookies|tous droits réservés|all rights reserved|cliquez ici|contactez-nous)",
            "",
            clean_text,
        )
        clean_text = clean_text.strip()

        if len(clean_text) > max_length:
            clean_text = f"{clean_text[:max_length]}... [TRUNCATED_WEB]"

        return clean_text


class NormalizationPipeline:
    PIPELINE_VERSION = "1.1.0"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.normalization_service = TextNormalizationService()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _join_subject_and_body(raw_content: dict[str, Any]) -> str:
        subject = str(raw_content.get("subject", "")).strip()
        body = str(raw_content.get("body", "")).strip()
        return f"Objet : {subject}\n\n{body}" if subject and body else body or subject

    @staticmethod
    def _map_binary_label(value: Any) -> NormalizedLabel | None:
        if value in {1, "1", True, "phishing"}:
            return NormalizedLabel.PHISHING
        if value in {0, "0", False, "legitimate", "ham"}:
            return NormalizedLabel.LEGITIMATE
        return None

    def _normalize_payload_text(
        self,
        source_name: str,
        raw_content: dict[str, Any],
    ) -> tuple[str | None, bool, RedactionStatus]:
        match source_name:
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
                candidate_text = str(
                    raw_content.get("text") or ""
                ).strip() or self._join_subject_and_body(raw_content)
            case _:
                candidate_text = str(raw_content.get("text") or "").strip()

        artifact = self.normalization_service.normalize_text(candidate_text)
        if not artifact.is_usable:
            return (
                None,
                artifact.contains_redaction_tokens,
                RedactionStatus.NOT_REQUIRED,
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
        )

    def extract_payload(
        self, source_name: str, raw_content: dict[str, Any]
    ) -> ExtractedPayload:
        cleaned_text, contains_pii, redaction_status = self._normalize_payload_text(
            source_name,
            raw_content,
        )

        label: NormalizedLabel | None
        match source_name:
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
                label = self._map_binary_label(raw_content.get("label"))
            case "common-crawl-bigdata":
                label = self._map_binary_label(raw_content.get("label"))
                if label is None:
                    label = self._map_binary_label(raw_content.get("category"))
            case "cert-fr-cti":
                label = NormalizedLabel.PHISHING
            case _:
                label = None

        return ExtractedPayload(
            text=cleaned_text,
            label=label,
            contains_pii=contains_pii,
            redaction_status=redaction_status,
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
        if source_system_name:
            for sid, sname in sources.items():
                if sname == source_system_name:
                    target_source_id = sid
                    break

            if not target_source_id:
                logger.error(f"Source system {source_system_name} not found.")
                return {
                    "status": "error",
                    "message": f"Source {source_system_name} not found.",
                }

        # 2. Find Raw Records that have NOT been normalized AND are natively French
        query = (
            select(DataRawRecord)
            .where(
                ~DataRawRecord.normalized_messages.any(),  # NOT EXISTS relationship
                DataRawRecord.detected_language == "fr",  # Tri-path isolation
                DataRawRecord.is_usable.is_(True),
            )
            .limit(batch_size)
        )
        if target_source_id:
            query = query.where(DataRawRecord.source_system_id == target_source_id)

        result = await self.session.execute(query)
        records = result.scalars().all()

        if not records:
            logger.info("No pending French raw records found.")
            return {"normalized": 0, "skipped": 0, "dry_run": dry_run}

        logger.info(f"Found {len(records)} raw records to process.")

        if dry_run:
            samples = []
            for rec in records:
                source_name = sources.get(rec.source_system_id, "unknown")
                raw_dict = json.loads(rec.raw_content)
                payload = self.extract_payload(source_name, raw_dict)
                if payload.text:
                    samples.append(
                        {
                            "source": source_name,
                            "extracted_label": payload.label,
                            "text_sample": payload.text[:200].replace("\n", " ")
                            + "...",
                        }
                    )
            return {
                "status": "dry-run success",
                "processed": len(records),
                "samples": samples,
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
            source_name = sources.get(rec.source_system_id, "unknown")
            try:
                raw_dict = json.loads(rec.raw_content)
                payload = self.extract_payload(source_name, raw_dict)

                if not payload.text or payload.label is None:
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
