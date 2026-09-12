"""What the workspace sees of its mail: KPIs, the threat journal, feedback, support."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.rate_limit import limiter
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import (
    FeedbackResponse,
    KpiResponse,
    SupportResponse,
    ThreatLogResponse,
    ThreatPageResponse,
    ThreatVisibilityResponse,
)
from data_platform.api.workspace_scope import owned_domain, workspace_threat_count
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["app-ui-flows"])


class StatusUpdate(BaseModel):
    status: str


class ThreatVisibilityUpdate(BaseModel):
    """Workspace-scoped visibility change that preserves audit evidence."""

    ids: list[str] = Field(min_length=1, max_length=100)
    hidden: bool


class FeedbackCreate(BaseModel):
    event_id: str | None = Field(default=None, max_length=120)
    feedback_type: str = Field(
        ...,
        pattern="^(false_negative|false_positive|true_positive|true_negative)$",
    )
    corrected_verdict: str = Field(
        ...,
        pattern="^(phishing|spam|legitimate|quarantine)$",
    )
    reporter_note: str | None = Field(default=None, max_length=500)


class SupportRequestCreate(BaseModel):
    requester_name: str = Field(min_length=2, max_length=120)
    requester_email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    category: str = Field(pattern="^(incident|dns|billing|feedback|other)$")
    message: str = Field(min_length=10, max_length=4000)


@router.get("/v1/stats/kpi", response_model=KpiResponse)
async def get_kpis(
    domain: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    raw_count = await workspace_threat_count(current_user.workspace_id, active_domain)
    norm_count = raw_count
    dataset_item_count = 0

    phishing_count = 0
    spam_count = 0
    legitimate_count = 0

    rows = await execute_runtime_query(
        "SELECT COALESCE(label_verdict, CASE WHEN safety_verdict = 'safe' "
        "THEN 'legitimate' ELSE safety_verdict END) AS label_verdict, COUNT(*) as cnt "
        "FROM app_inference_event WHERE workspace_id = ? AND lower(domain) = lower(?) GROUP BY 1",
        (current_user.workspace_id, active_domain),
    )
    for row in rows:
        verdict = row["label_verdict"]
        count = row["cnt"]
        if verdict in ("phishing", "quarantine"):
            phishing_count += count
        elif verdict == "spam":
            spam_count = count
        elif verdict == "legitimate":
            legitimate_count = count

    return {
        "raw_records_count": raw_count,
        "normalized_messages_count": norm_count,
        "dataset_items_count": dataset_item_count,
        "threats_phishing_count": phishing_count,
        "threats_spam_count": spam_count,
        "threats_legitimate_count": legitimate_count,
        "domain": active_domain,
    }


def _serialize_threat(row: dict[str, object]) -> dict[str, object]:
    """Return the privacy-preserving customer representation of an event."""
    status = row.get("status")
    if status not in ("active", "trashed", "restored"):
        status = "active"
    verdict = str(row.get("verdict") or "legitimate")
    is_anonymized = verdict not in ("phishing", "quarantine")
    identifier = str(row["id"])
    return {
        "id": identifier,
        "message_id": row.get("message_id"),
        "privacy_reference": f"MSG-{identifier.replace('-', '')[:8].upper()}",
        "content_redacted": is_anonymized,
        "subject": "[Masqué par Sicurre]" if is_anonymized else row.get("subject"),
        "sender": "[Masqué par Sicurre]" if is_anonymized else row.get("sender"),
        "body_preview": "[Masqué par Sicurre]" if is_anonymized else row.get("body_preview"),
        "verdict": verdict,
        "confidence": row.get("confidence"),
        "received_at": row.get("received_at"),
        "status": status,
        "latency_ms": row.get("latency_ms"),
        "explanation": row.get("explanation"),
    }


@router.get("/v1/threats", response_model=ThreatPageResponse)
async def get_threats(
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
    page: int = 1,
    page_size: int = 10,
    verdict: str = "all",
    date_range: str = "all",
    search: str = "",
    hidden: bool = False,
):
    """Return one filtered page of workspace events."""
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    if verdict not in {"all", "phishing", "spam", "legitimate"}:
        raise HTTPException(status_code=400, detail="Invalid verdict filter")
    if date_range not in {"all", "today", "7d", "month", "last_month"}:
        raise HTTPException(status_code=400, detail="Invalid date filter")

    active_domain = await owned_domain(domain, current_user)
    verdict_expr = (
        "COALESCE(label_verdict, CASE WHEN safety_verdict = 'safe' "
        "THEN 'legitimate' ELSE safety_verdict END)"
    )
    where = ["workspace_id = ?", "lower(domain) = lower(?)", "COALESCE(is_deleted, 0) = ?"]
    params: list[object] = [current_user.workspace_id, active_domain, 1 if hidden else 0]
    if verdict == "phishing":
        where.append(f"{verdict_expr} IN ('phishing', 'quarantine')")
    elif verdict != "all":
        where.append(f"{verdict_expr} = ?")
        params.append(verdict)

    now = datetime.now(timezone.utc)
    if date_range == "today":
        where.append("created_at >= ?")
        params.append(now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat())
    elif date_range == "7d":
        where.append("created_at >= ?")
        params.append((now - timedelta(days=7)).isoformat())
    elif date_range == "month":
        where.append("created_at >= ?")
        params.append(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat())
    elif date_range == "last_month":
        this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previous_month = (this_month - timedelta(days=1)).replace(day=1)
        where.extend(["created_at >= ?", "created_at < ?"])
        params.extend([previous_month.isoformat(), this_month.isoformat()])

    normalized_search = search.strip()[:120]
    if normalized_search:
        token = f"%{normalized_search.lower()}%"
        where.append(
            "(LOWER(COALESCE(subject, '')) LIKE ? OR LOWER(COALESCE(sender, '')) LIKE ? "
            "OR LOWER(REPLACE(id, '-', '')) LIKE ?)"
        )
        params.extend([token, token, token.replace("msg-", "")])

    where_sql = " AND ".join(where)
    count_rows = await execute_runtime_query(
        f"SELECT COUNT(*) AS total FROM app_inference_event WHERE {where_sql}",
        tuple(params),
    )
    total = int(count_rows[0]["total"]) if count_rows else 0
    rows = await execute_runtime_query(
        f"""
            SELECT
                id,
                id AS message_id,
                subject,
                sender,
                snippet AS body_preview,
                {verdict_expr} AS verdict,
                composite_score AS confidence,
                created_at AS received_at,
                COALESCE(override_verdict, 'active') AS status,
                latency_ms,
                explanation,
                model_version,
                model_revision
            FROM app_inference_event
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
        (*params, page_size, (page - 1) * page_size),
    )
    return {
        "items": [_serialize_threat(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("/v1/threats/visibility", response_model=ThreatVisibilityResponse)
async def update_threat_visibility(
    payload: ThreatVisibilityUpdate,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    """Hide or restore selected events without deleting their audit evidence."""
    active_domain = await owned_domain(domain, current_user)
    placeholders = ", ".join("?" for _ in payload.ids)
    existing = await execute_runtime_query(
        f"SELECT id FROM app_inference_event WHERE workspace_id = ? AND lower(domain) = lower(?) AND id IN ({placeholders})",
        (current_user.workspace_id, active_domain, *payload.ids),
    )
    existing_ids = {str(row["id"]) for row in existing}
    if len(existing_ids) != len(set(payload.ids)):
        raise HTTPException(status_code=404, detail="Threat not found")
    await execute_runtime_query(
        f"UPDATE app_inference_event SET is_deleted = ? WHERE workspace_id = ? AND lower(domain) = lower(?) AND id IN ({placeholders})",
        (1 if payload.hidden else 0, current_user.workspace_id, active_domain, *payload.ids),
    )
    return {"updated": len(existing_ids), "hidden": payload.hidden}


@router.post(
    "/v1/threats/{id}/status",
    response_model=ThreatLogResponse,
    response_model_exclude_unset=True,
)
async def update_threat_status(
    id: str,
    payload: StatusUpdate,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    if payload.status not in ("active", "trashed", "restored"):
        raise HTTPException(status_code=400, detail="Invalid status value")
    active_domain = await owned_domain(domain, current_user)
    try:
        is_del = 1 if payload.status == "trashed" else 0
        await execute_runtime_query(
            "UPDATE app_inference_event SET is_deleted = ?, override_verdict = ?, overridden_at = ? WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?)",
            (
                is_del,
                payload.status,
                datetime.now(timezone.utc).isoformat(),
                id,
                current_user.workspace_id,
                active_domain,
            ),
        )
        rows = await execute_runtime_query(
            "SELECT id, id AS message_id, subject, sender, snippet AS body_preview, "
            "COALESCE(label_verdict, CASE WHEN safety_verdict = 'safe' THEN 'legitimate' "
            "ELSE safety_verdict END) AS verdict, composite_score AS confidence, "
            "created_at AS received_at, override_verdict AS status "
            "FROM app_inference_event WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?)",
            (id, current_user.workspace_id, active_domain),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Threat not found")
        row = rows[0]
        verdict = row["verdict"]
        is_anonymized = verdict not in ("phishing", "quarantine")
        return {
            "id": row["id"],
            "message_id": row["message_id"],
            "privacy_reference": f"MSG-{str(row['id']).replace('-', '')[:8].upper()}",
            "content_redacted": is_anonymized,
            "subject": "[Masqué par Sicurre]" if is_anonymized else row["subject"],
            "sender": "[Masqué par Sicurre]" if is_anonymized else row["sender"],
            "body_preview": "[Masqué par Sicurre]" if is_anonymized else row["body_preview"],
            "verdict": verdict,
            "confidence": row["confidence"],
            "received_at": row["received_at"],
            "status": (
                row["status"] if row["status"] in ("active", "trashed", "restored") else "active"
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Threat status update failed")
        raise HTTPException(status_code=500, detail="Unable to update threat status") from exc


@router.post("/v1/feedback", status_code=201, response_model=FeedbackResponse)
async def create_feedback(
    payload: FeedbackCreate,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    event_row = None
    if payload.event_id:
        rows = await execute_runtime_query(
            """
            SELECT id, safety_verdict
            FROM app_inference_event
            WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?)
            LIMIT 1
            """,
            (payload.event_id, current_user.workspace_id, active_domain),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Linked event not found")
        event_row = rows[0]

    feedback_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat() + "Z"
    original_verdict = event_row["safety_verdict"] if event_row else None

    try:
        await execute_runtime_query(
            """
            INSERT INTO app_feedback (
                id, workspace_id, workspace_member_user_id, event_id,
                feedback_type, original_verdict, corrected_verdict,
                reporter_note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                current_user.workspace_id,
                current_user.id,
                payload.event_id,
                payload.feedback_type,
                original_verdict,
                payload.corrected_verdict,
                (payload.reporter_note or "").strip() or None,
                now,
            ),
        )
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message:
            raise HTTPException(status_code=409, detail="Feedback already submitted") from exc
        raise HTTPException(status_code=500, detail="Could not record feedback") from exc

    if payload.event_id:
        override_status = (
            "reported_false_negative"
            if payload.feedback_type == "false_negative"
            else "reported_false_positive"
        )
        await execute_runtime_query(
            """
            UPDATE app_inference_event
            SET override_verdict = ?, overridden_at = ?
            WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?)
            """,
            (
                override_status,
                now,
                payload.event_id,
                current_user.workspace_id,
                active_domain,
            ),
        )

    return {
        "id": feedback_id,
        "event_id": payload.event_id,
        "feedback_type": payload.feedback_type,
        "original_verdict": original_verdict,
        "corrected_verdict": payload.corrected_verdict,
        "created_at": now,
    }


@router.post("/v1/support/requests", status_code=201, response_model=SupportResponse)
@limiter.limit("10/hour")
async def create_support_request(
    request: Request,
    payload: SupportRequestCreate,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    """Create a durable tenant-scoped support ticket."""
    _ = request
    ticket_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await execute_runtime_query(
        "INSERT INTO app_support_request (id, workspace_id, workspace_member_user_id, "
        "requester_name, requester_email, category, message, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
        (
            ticket_id,
            current_user.workspace_id,
            current_user.id,
            payload.requester_name.strip(),
            payload.requester_email.strip().lower(),
            payload.category,
            payload.message.strip(),
            now,
            now,
        ),
    )
    return {"id": ticket_id, "status": "open", "created_at": now}
