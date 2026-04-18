from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AnnotationLabelSource,
    DataAnnotation,
    DataNormalizedMessage,
    DataProcessingRun,
    DataRawRecord,
    DataSourceSystem,
)


@dataclass(slots=True)
class MissingAnnotationRow:
    normalized_message_id: object
    current_label: str
    source_system_name: str | None
    pipeline_version: str | None


class AnnotationBackfillService:
    @staticmethod
    def _build_missing_annotations_query(
        *,
        source_names: tuple[str, ...] | None = None,
    ) -> Select[tuple[object, str, str | None, str | None]]:
        query = (
            select(
                DataNormalizedMessage.id,
                DataNormalizedMessage.current_label,
                DataSourceSystem.name,
                DataProcessingRun.pipeline_version,
            )
            .select_from(DataNormalizedMessage)
            .join(
                DataRawRecord, DataNormalizedMessage.raw_record_id == DataRawRecord.id
            )
            .join(
                DataSourceSystem, DataRawRecord.source_system_id == DataSourceSystem.id
            )
            .join(
                DataProcessingRun,
                DataNormalizedMessage.processing_run_id == DataProcessingRun.id,
            )
            .outerjoin(
                DataAnnotation,
                DataAnnotation.normalized_message_id == DataNormalizedMessage.id,
            )
            .where(DataAnnotation.id.is_(None))
            .order_by(DataSourceSystem.name, DataNormalizedMessage.id)
        )
        if source_names:
            query = query.where(DataSourceSystem.name.in_(source_names))
        return query

    @staticmethod
    def _resolve_label_source(
        *,
        source_system_name: str | None,
        pipeline_version: str | None,
    ) -> str:
        resolved_source = str(source_system_name or "")
        resolved_pipeline = str(pipeline_version or "")
        if resolved_source.startswith("synthetic-generated-"):
            return AnnotationLabelSource.GENERATION_GATED_PROMOTION.value
        if resolved_pipeline.startswith("common_crawl_reviewed_promotion"):
            return AnnotationLabelSource.COMMON_CRAWL_ACCEPTANCE_REVIEW.value
        return AnnotationLabelSource.NORMALIZED_MESSAGE_BACKFILL.value

    @classmethod
    async def backfill_missing_annotations(
        cls,
        session: AsyncSession,
        *,
        source_names: tuple[str, ...] | None = None,
        dry_run: bool,
    ) -> dict[str, object]:
        rows = [
            MissingAnnotationRow(*row)
            for row in (
                await session.execute(
                    cls._build_missing_annotations_query(source_names=source_names)
                )
            ).all()
        ]
        started_at = datetime.now(timezone.utc)
        label_counts: Counter[str] = Counter()
        source_counts: Counter[tuple[str, str]] = Counter()

        for row in rows:
            label_counts.update([row.current_label])
            label_source = cls._resolve_label_source(
                source_system_name=row.source_system_name,
                pipeline_version=row.pipeline_version,
            )
            source_counts.update(
                [(label_source, str(row.source_system_name or "unknown"))]
            )

        if dry_run:
            return {
                "mode": "preview",
                "annotation_count": len(rows),
                "label_totals": dict(label_counts),
                "source_totals": [
                    {
                        "label_source": label_source,
                        "source_system_name": source_name,
                        "row_count": row_count,
                    }
                    for (label_source, source_name), row_count in sorted(
                        source_counts.items()
                    )
                ],
            }

        session.add_all(
            [
                DataAnnotation(
                    normalized_message_id=row.normalized_message_id,
                    label=row.current_label,
                    label_source=cls._resolve_label_source(
                        source_system_name=row.source_system_name,
                        pipeline_version=row.pipeline_version,
                    ),
                    confidence=1.0,
                    comment="Backfilled from current_label on curated normalized message.",
                    is_validated=False,
                    annotated_at=started_at,
                )
                for row in rows
            ]
        )
        await session.commit()
        return {
            "mode": "write",
            "annotation_count": len(rows),
            "label_totals": dict(label_counts),
            "source_totals": [
                {
                    "label_source": label_source,
                    "source_system_name": source_name,
                    "row_count": row_count,
                }
                for (label_source, source_name), row_count in sorted(
                    source_counts.items()
                )
            ],
        }
