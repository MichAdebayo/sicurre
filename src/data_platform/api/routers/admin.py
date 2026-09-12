"""Platform admin routes: overview, domain inventory, runtime health, pipeline."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_async_session
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import (
    AdminDomainPageResponse,
    AdminOverviewResponse,
    AdminRuntimeHealthResponse,
    DatasetSummaryResponse,
    PipelineRunResponse,
)
from data_platform.services.runtime_probes import (
    component_rollup,
    probe_cloudflare_runtime,
    probe_inference_runtime,
    probe_public_app_runtime,
    quarantine_storage_status,
    quiet_count,
    quiet_rows,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["app-ui-flows"])


@router.get("/v1/admin/runtime-health", response_model=AdminRuntimeHealthResponse)
async def get_admin_runtime_health(current_user: AuthUser = Depends(get_current_user)):
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")

    settings = get_settings()
    async with httpx.AsyncClient(timeout=6.0) as client:
        inference_components = await probe_inference_runtime(
            client, settings.inference_api_url, settings.inference_api_key
        )
        public_app_components, expected_scan_url = await probe_public_app_runtime(
            client,
            settings.public_api_url,
            settings.internal_app_probe_url,
        )
        cloudflare_components = await probe_cloudflare_runtime(
            client,
            expected_scan_url=expected_scan_url,
        )

    components = (
        inference_components
        + public_app_components
        + cloudflare_components
        + [quarantine_storage_status()]
    )
    parsed_public = urlparse(settings.public_api_url or "")
    return {
        "status": component_rollup(components),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "public_api_host": parsed_public.netloc or None,
        "inference_api_url": settings.inference_api_url,
        "expected_worker_scan_url": expected_scan_url,
        "components": components,
    }


@router.get("/v1/admin/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(current_user: AuthUser = Depends(get_current_user)):
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")

    overview = {
        "workspaces_count": await quiet_count("SELECT COUNT(*) AS count FROM app_workspace"),
        "members_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM app_workspace_membership"
        ),
        "threat_events_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM app_inference_event WHERE (is_deleted IS NULL OR is_deleted = 0)"
        ),
        "feedback_count": await quiet_count("SELECT COUNT(*) AS count FROM app_feedback"),
        "false_negative_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM app_feedback WHERE feedback_type = 'false_negative'"
        ),
        "reported_email_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM app_reported_email"
        ),
        "quarantine_held_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM app_quarantine_item WHERE status = 'held'"
        ),
        "cloudflare_integrations_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM cloudflare_integration"
        ),
        "cloudflare_active_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM cloudflare_integration WHERE status = 'active'"
        ),
        "support_open_count": await quiet_count(
            "SELECT COUNT(*) AS count FROM app_support_request WHERE status = 'open'"
        ),
    }

    verdict_rows = await quiet_rows(
        """
        SELECT
            COALESCE(label_verdict, CASE WHEN safety_verdict = 'safe' THEN 'legitimate' ELSE safety_verdict END) AS verdict,
            COUNT(*) AS count
        FROM app_inference_event
        WHERE (is_deleted IS NULL OR is_deleted = 0)
        GROUP BY 1
        """
    )
    feedback_rows = await quiet_rows(
        """
        SELECT feedback_type, COUNT(*) AS count
        FROM app_feedback
        GROUP BY feedback_type
        """
    )
    domain_rows = await quiet_rows(
        """
        SELECT zone_name, status, user_email, updated_at
        FROM cloudflare_integration
        ORDER BY updated_at DESC
        LIMIT 8
        """
    )

    recent_feedback = await quiet_rows(
        """
        SELECT
            f.id,
            f.workspace_id,
            f.feedback_type,
            f.original_verdict,
            f.corrected_verdict,
            f.created_at,
            m.email AS reporter_email
        FROM app_feedback f
        LEFT JOIN app_workspace_membership m ON m.auth_user_id = f.workspace_member_user_id
        ORDER BY f.created_at DESC
        LIMIT 8
        """
    )
    recent_quarantine = await quiet_rows(
        """
        SELECT id, workspace_id, safety_verdict, composite_score, status, created_at, expires_at
        FROM app_quarantine_item
        ORDER BY created_at DESC
        LIMIT 8
        """
    )
    recent_support = await quiet_rows(
        "SELECT id, workspace_id, requester_email, category, status, created_at "
        "FROM app_support_request ORDER BY created_at DESC LIMIT 8"
    )

    return {
        "summary": overview,
        "verdicts": verdict_rows,
        "feedback_by_type": feedback_rows,
        "cloudflare_domains": domain_rows,
        "recent_feedback": recent_feedback,
        "recent_quarantine": recent_quarantine,
        "recent_support": recent_support,
    }


@router.get("/v1/admin/domains", response_model=AdminDomainPageResponse)
async def get_admin_domains(
    current_user: AuthUser = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    search: str = "",
):
    """Return a bounded, searchable Cloudflare integration inventory."""
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    normalized_search = search.strip()[:120]
    where = ""
    params: tuple[object, ...] = ()
    if normalized_search:
        where = (
            "WHERE LOWER(COALESCE(zone_name, '')) LIKE ? OR LOWER(COALESCE(user_email, '')) LIKE ?"
        )
        token = f"%{normalized_search.lower()}%"
        params = (token, token)
    total = await quiet_count(
        f"SELECT COUNT(*) AS count FROM cloudflare_integration {where}", params
    )
    items = await quiet_rows(
        f"SELECT zone_name, status, user_email, updated_at FROM cloudflare_integration {where} "
        "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (*params, page_size, (page - 1) * page_size),
    )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/v1/datasets", response_model=list[DatasetSummaryResponse])
async def list_datasets_alias(
    session: AsyncSession = Depends(get_async_session),
    current_user: AuthUser = Depends(get_current_user),
):
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    try:
        result = await session.execute(
            text(
                "SELECT id, version_tag, item_count, status, published_at FROM data_dataset ORDER BY version_tag DESC"
            )
        )
        rows = result.all()
        return [
            {
                "id": str(row.id),
                "version_tag": row.version_tag,
                "item_count": row.item_count,
                "status": row.status,
                "published_at": (f"{row.published_at.isoformat()}Z" if row.published_at else None),
            }
            for row in rows
        ]
    except Exception:
        return []


def execute_pipeline():
    try:
        subprocess.run(["make", "run-scheduler"], check=True)
    except Exception:
        logger.exception("Scheduled pipeline execution failed")


@router.post("/v1/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
):
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    background_tasks.add_task(execute_pipeline)
    return {"run_id": "incremental-pipeline-run-triggered"}
