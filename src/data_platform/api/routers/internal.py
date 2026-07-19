from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.rate_limit import limiter, touch_rate_limit_request
from core.security import require_internal_key
from data_platform.api.schemas.mlops import (
    EvaluationSetRegistration,
    LineageRecordResponse,
    ModelCandidateRegistration,
    ModelDeploymentRegistration,
    ModelEvaluationRegistration,
)
from data_platform.services.model_provenance import (
    ModelProvenanceError,
    register_candidate,
    register_deployment,
    register_evaluation,
    register_evaluation_set,
)
from db.models.lineage import DataRawRecord, DataSourceSystem

router = APIRouter(prefix="/internal", tags=["internal"])

_PHISHTANK_SOURCE_NAME = "phishtank-online-valid"
InternalAuth = Annotated[None, Depends(require_internal_key)]
DatabaseSession = Annotated[AsyncSession, Depends(get_async_session)]


def _provenance_error(exc: ModelProvenanceError) -> HTTPException:
    """Map bounded lineage failures without leaking persistence details."""
    conflict_codes = {
        "candidate_conflict",
        "deployment_conflict",
        "evaluation_conflict",
        "evaluation_set_conflict",
    }
    return HTTPException(
        status_code=(
            status.HTTP_409_CONFLICT
            if exc.code in conflict_codes
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        ),
        detail={"code": exc.code, "message": str(exc)},
    )


async def _persist_lineage(operation: Any) -> LineageRecordResponse:
    """Execute one provenance operation with stable API error mapping."""
    try:
        record = await operation
    except ModelProvenanceError as exc:
        raise _provenance_error(exc) from exc
    return LineageRecordResponse(id=record.id, status=record.status, idempotent=record.idempotent)


@router.post("/ml/evaluation-sets", response_model=LineageRecordResponse)
@limiter.limit("10/minute")
async def persist_evaluation_set(
    request: Request,
    payload: EvaluationSetRegistration,
    _: InternalAuth,
    session: DatabaseSession,
) -> LineageRecordResponse:
    """Register or approve an immutable evaluation-only asset."""
    touch_rate_limit_request(request)
    return await _persist_lineage(register_evaluation_set(session, payload))


@router.post("/ml/candidates", response_model=LineageRecordResponse)
@limiter.limit("10/minute")
async def persist_model_candidate(
    request: Request,
    payload: ModelCandidateRegistration,
    _: InternalAuth,
    session: DatabaseSession,
) -> LineageRecordResponse:
    """Register a successful training result as a non-production candidate."""
    touch_rate_limit_request(request)
    return await _persist_lineage(register_candidate(session, payload))


@router.post("/ml/evaluations", response_model=LineageRecordResponse)
@limiter.limit("10/minute")
async def persist_model_evaluation(
    request: Request,
    payload: ModelEvaluationRegistration,
    _: InternalAuth,
    session: DatabaseSession,
) -> LineageRecordResponse:
    """Record a golden-set decision and its authoritative MLflow reference."""
    touch_rate_limit_request(request)
    return await _persist_lineage(register_evaluation(session, payload))


@router.post("/ml/deployments", response_model=LineageRecordResponse)
@limiter.limit("10/minute")
async def persist_model_deployment(
    request: Request,
    payload: ModelDeploymentRegistration,
    _: InternalAuth,
    session: DatabaseSession,
) -> LineageRecordResponse:
    """Record a manually approved promotion workflow result."""
    touch_rate_limit_request(request)
    return await _persist_lineage(register_deployment(session, payload))


@router.get("/phishtank/snapshot")
@limiter.limit("10/minute")
async def get_phishtank_snapshot(
    request: Request,
    _: InternalAuth,
    session: DatabaseSession,
    since: Annotated[
        datetime | None,
        Query(description="ISO 8601 timestamp — only return URLs extracted after this time"),
    ] = None,
) -> dict:
    """Return all known PhishTank phishing URLs for classifier pipeline use.

    Intended for service-to-service calls only (e.g. from sicurre-ml).
    Pass ``since`` for incremental updates after the initial seed load.
    """
    touch_rate_limit_request(request)

    source_stmt = select(DataSourceSystem).where(
        DataSourceSystem.name == _PHISHTANK_SOURCE_NAME
    )
    source_result = await session.execute(source_stmt)
    source = source_result.scalar_one_or_none()

    if source is None:
        return {
            "urls": [],
            "count": 0,
            "source": _PHISHTANK_SOURCE_NAME,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    stmt = select(DataRawRecord.raw_content, DataRawRecord.extracted_at).where(
        DataRawRecord.source_system_id == source.id,
        DataRawRecord.is_usable.is_(True),
    )
    if since is not None:
        stmt = stmt.where(DataRawRecord.extracted_at > since)

    result = await session.execute(stmt)
    rows = result.all()

    urls: list[str] = []
    for raw_content, _ in rows:
        try:
            data = json.loads(raw_content)
            url = data.get("url")
            if url:
                urls.append(url)
        except (json.JSONDecodeError, TypeError):
            continue

    return {
        "urls": urls,
        "count": len(urls),
        "source": _PHISHTANK_SOURCE_NAME,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
