from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from data_platform.services.database.source_naming import (
    DATABASE_PARENT_SOURCE,
    DATABASE_SOURCE_PREFIX,
)
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
    def _build_source_name_filter(
        source_names: tuple[str, ...] | None,
    ) -> object | None:
        if not source_names:
            return None

        normalized_source_names = {
            str(source_name).strip()
            for source_name in source_names
            if str(source_name).strip()
        }
        if not normalized_source_names:
            return None

        conditions: list[object] = []
        exact_source_names = sorted(
            source_name
            for source_name in normalized_source_names
            if source_name != DATABASE_PARENT_SOURCE
        )
        if exact_source_names:
            conditions.append(DataSourceSystem.name.in_(exact_source_names))

        if DATABASE_PARENT_SOURCE in normalized_source_names:
            conditions.extend(
                [
                    DataSourceSystem.name == DATABASE_PARENT_SOURCE,
                    DataSourceSystem.name.like(f"{DATABASE_SOURCE_PREFIX}%"),
                ]
            )

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return or_(*conditions)

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
        source_filter = AnnotationBackfillService._build_source_name_filter(
            source_names
        )
        if source_filter is not None:
            query = query.where(source_filter)
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
        started_at = datetime.now(UTC)
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
