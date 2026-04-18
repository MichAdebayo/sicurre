from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.config import get_settings  # noqa: E402
from core.trace_logger import SemanticTraceLogger  # noqa: E402
from db.models import (  # noqa: E402
    DataIngestionRun,
    DataNormalizedMessage,
    DataRawObject,
    DataRawRecord,
    DataSourceSystem,
)


@dataclass(frozen=True)
class CronJobSpec:
    name: str
    label: str
    script_path: Path
    source_names: tuple[str, ...] = ()
    source_type: str | None = None


CRON_JOBS: tuple[CronJobSpec, ...] = (
    CronJobSpec(
        name="phishtank",
        label="PhishTank",
        script_path=ROOT_DIR
        / "src/data_platform/cron_schedulers/api/run_phishtank_ingestion.py",
        source_names=("phishtank-online-valid",),
    ),
    CronJobSpec(
        name="certfr",
        label="CERT-FR CTI",
        script_path=ROOT_DIR
        / "src/data_platform/cron_schedulers/scraping/run_certfr_cti.py",
        source_names=("cert-fr-cti",),
    ),
    CronJobSpec(
        name="csv",
        label="CSV File Sources",
        script_path=ROOT_DIR
        / "src/data_platform/cron_schedulers/file/run_csv_ingestion.py",
        source_type="file",
    ),
    CronJobSpec(
        name="database_historical",
        label="Database Historical Feed",
        script_path=ROOT_DIR
        / "src/data_platform/cron_schedulers/database/run_database_historical_feed.py",
        source_names=("database-historical",),
    ),
    CronJobSpec(
        name="common_crawl",
        label="Common Crawl",
        script_path=ROOT_DIR
        / "src/data_platform/cron_schedulers/bigdata/run_common_crawl_pipeline.py",
        source_names=("common-crawl-bigdata",),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the scheduled cron suite manually and summarize DB deltas."
    )
    parser.add_argument(
        "--job",
        action="append",
        choices=[job.name for job in CRON_JOBS],
        help="Optional subset of jobs to run. May be provided multiple times.",
    )
    parser.add_argument(
        "--reset-scheduled",
        action="store_true",
        help="Delete prior scheduled ingestion runs for the selected cron jobs before executing the suite.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running later cron jobs even if an earlier one fails.",
    )
    return parser.parse_args()


def _selected_jobs(job_names: list[str] | None) -> list[CronJobSpec]:
    if not job_names:
        return list(CRON_JOBS)
    selected = set(job_names)
    return [job for job in CRON_JOBS if job.name in selected]


async def _resolve_source_rows(
    session: AsyncSession,
    *,
    source_names: tuple[str, ...],
    source_type: str | None,
) -> list[tuple[object, str]]:
    stmt = select(DataSourceSystem.id, DataSourceSystem.name)
    if source_names:
        stmt = stmt.where(DataSourceSystem.name.in_(source_names))
    if source_type is not None:
        stmt = stmt.where(DataSourceSystem.source_type == source_type)
    rows = await session.execute(stmt)
    return [(source_id, str(name)) for source_id, name in rows.all()]


async def _source_summary(session: AsyncSession, job: CronJobSpec) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    source_rows = await _resolve_source_rows(
        session,
        source_names=job.source_names,
        source_type=job.source_type,
    )
    for source_id, source_name in source_rows:
        ingestion_runs = int(
            await session.scalar(
                select(func.count(DataIngestionRun.id)).where(
                    DataIngestionRun.source_system_id == source_id,
                    DataIngestionRun.trigger_mode == "scheduled",
                )
            )
            or 0
        )
        raw_objects = int(
            await session.scalar(
                select(func.count(DataRawObject.id))
                .join(
                    DataIngestionRun,
                    DataRawObject.ingestion_run_id == DataIngestionRun.id,
                )
                .where(
                    DataIngestionRun.source_system_id == source_id,
                    DataIngestionRun.trigger_mode == "scheduled",
                )
            )
            or 0
        )
        raw_records = int(
            await session.scalar(
                select(func.count(DataRawRecord.id))
                .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
                .join(
                    DataIngestionRun,
                    DataRawObject.ingestion_run_id == DataIngestionRun.id,
                )
                .where(
                    DataIngestionRun.source_system_id == source_id,
                    DataIngestionRun.trigger_mode == "scheduled",
                )
            )
            or 0
        )
        latest_run = await session.scalar(
            select(DataIngestionRun)
            .where(
                DataIngestionRun.source_system_id == source_id,
                DataIngestionRun.trigger_mode == "scheduled",
            )
            .order_by(DataIngestionRun.started_at.desc())
            .limit(1)
        )
        summary[source_name] = {
            "ingestion_runs": ingestion_runs,
            "raw_objects": raw_objects,
            "raw_records": raw_records,
            "latest_run": None,
        }
        if latest_run is not None:
            summary[source_name]["latest_run"] = {
                "id": str(latest_run.id),
                "status": latest_run.status,
                "started_at": latest_run.started_at.isoformat(),
                "finished_at": (
                    latest_run.finished_at.isoformat()
                    if latest_run.finished_at is not None
                    else None
                ),
                "raw_object_count": latest_run.raw_object_count,
                "raw_record_count": latest_run.raw_record_count,
                "log_message": latest_run.log_message,
            }
    return summary


def _summary_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    source_names = sorted(set(before) | set(after))
    delta: dict[str, Any] = {}
    for source_name in source_names:
        before_row = before.get(source_name, {})
        after_row = after.get(source_name, {})
        delta[source_name] = {
            "ingestion_runs_delta": int(after_row.get("ingestion_runs", 0))
            - int(before_row.get("ingestion_runs", 0)),
            "raw_objects_delta": int(after_row.get("raw_objects", 0))
            - int(before_row.get("raw_objects", 0)),
            "raw_records_delta": int(after_row.get("raw_records", 0))
            - int(before_row.get("raw_records", 0)),
            "latest_run": after_row.get("latest_run"),
        }
    return delta


async def _reset_scheduled_runs(
    session: AsyncSession,
    job: CronJobSpec,
) -> dict[str, Any]:
    source_rows = await _resolve_source_rows(
        session,
        source_names=job.source_names,
        source_type=job.source_type,
    )
    source_ids = [source_id for source_id, _ in source_rows]
    if not source_ids:
        return {"deleted_runs": 0, "blocked": False, "reason": None}

    run_ids = list(
        (
            await session.scalars(
                select(DataIngestionRun.id).where(
                    DataIngestionRun.source_system_id.in_(source_ids),
                    DataIngestionRun.trigger_mode == "scheduled",
                )
            )
        ).all()
    )
    if not run_ids:
        return {"deleted_runs": 0, "blocked": False, "reason": None}

    normalized_count = int(
        await session.scalar(
            select(func.count(DataNormalizedMessage.id))
            .join(
                DataRawRecord,
                DataNormalizedMessage.raw_record_id == DataRawRecord.id,
            )
            .join(DataRawObject, DataRawRecord.raw_object_id == DataRawObject.id)
            .where(DataRawObject.ingestion_run_id.in_(run_ids))
        )
        or 0
    )
    if normalized_count > 0:
        return {
            "deleted_runs": 0,
            "blocked": True,
            "reason": (
                f"{normalized_count} normalized messages still depend on scheduled raw records"
            ),
        }

    raw_object_ids = list(
        (
            await session.scalars(
                select(DataRawObject.id).where(
                    DataRawObject.ingestion_run_id.in_(run_ids)
                )
            )
        ).all()
    )
    if raw_object_ids:
        await session.execute(
            delete(DataRawRecord).where(DataRawRecord.raw_object_id.in_(raw_object_ids))
        )
        await session.execute(
            delete(DataRawObject).where(DataRawObject.id.in_(raw_object_ids))
        )
    await session.execute(
        delete(DataIngestionRun).where(DataIngestionRun.id.in_(run_ids))
    )
    await session.commit()
    return {"deleted_runs": len(run_ids), "blocked": False, "reason": None}


async def _run_script(job: CronJobSpec) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(
        subprocess.run,
        [sys.executable, str(job.script_path)],
        cwd=str(ROOT_DIR),
        check=False,
        text=True,
    )


async def run_orchestrator(
    *,
    job_names: list[str] | None = None,
    reset_scheduled: bool = False,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    selected_jobs = _selected_jobs(job_names)
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    trace = SemanticTraceLogger(
        parent_type="Orchestration",
        child_target="Cron Suite",
        domain="data_platform",
        trace_id=f"cron-suite-{uuid.uuid4()}",
    )
    trace.trace(
        stage="orchestration",
        status="start",
        message="Cron suite starting",
        metrics={
            "job_count": len(selected_jobs),
            "reset_scheduled": int(reset_scheduled),
        },
    )

    payload: dict[str, Any] = {
        "database_url": settings.database_url,
        "jobs": [],
    }

    try:
        for job in selected_jobs:
            async with session_factory() as session:
                reset_result = (
                    await _reset_scheduled_runs(session, job)
                    if reset_scheduled
                    else {"deleted_runs": 0, "blocked": False, "reason": None}
                )
                before = await _source_summary(session, job)

            trace.trace(
                stage="orchestration",
                status="start",
                message=f"Starting cron job {job.label}",
                entity_type="cron_job",
                entity_id=job.name,
                metrics={
                    "tracked_sources": len(before),
                    "reset_deleted_runs": reset_result["deleted_runs"],
                },
            )
            completed = await _run_script(job)

            async with session_factory() as session:
                after = await _source_summary(session, job)

            delta = _summary_delta(before, after)
            payload["jobs"].append(
                {
                    "job": job.name,
                    "label": job.label,
                    "script_path": str(job.script_path.relative_to(ROOT_DIR)),
                    "exit_code": completed.returncode,
                    "reset": reset_result,
                    "before": before,
                    "after": after,
                    "delta": delta,
                }
            )

            status = "success" if completed.returncode == 0 else "failed"
            trace.trace(
                stage="orchestration",
                status=status,
                message=f"Cron job {job.label} finished with exit code {completed.returncode}",
                entity_type="cron_job",
                entity_id=job.name,
                metrics={
                    "exit_code": completed.returncode,
                    "raw_records_delta": sum(
                        row["raw_records_delta"] for row in delta.values()
                    ),
                },
            )

            if completed.returncode != 0 and not continue_on_error:
                break
    finally:
        await engine.dispose()

    trace.trace(
        stage="orchestration",
        status="success",
        message="Cron suite completed",
        metrics={"jobs_executed": len(payload["jobs"])},
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


async def main() -> None:
    args = parse_args()
    await run_orchestrator(
        job_names=args.job,
        reset_scheduled=args.reset_scheduled,
        continue_on_error=args.continue_on_error,
    )


if __name__ == "__main__":
    asyncio.run(main())
