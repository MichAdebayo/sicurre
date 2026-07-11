from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.rate_limit import limiter, touch_rate_limit_request
from db.models import IngestionStatus
from db.queries import SourceSystemNotFoundError
from data_platform.api.schemas import (
    IngestionRunCreate,
    IngestionRunListResponse,
    IngestionRunRead,
)
from db.services import IngestionRunService


router = APIRouter(tags=["data-ingestion"])
service = IngestionRunService()


@router.get("/ingestion-runs", response_model=IngestionRunListResponse)
@limiter.limit("60/minute")
async def list_ingestion_runs(
    request: Request,
    source_system_id: UUID | None = Query(default=None),
    status: IngestionStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> IngestionRunListResponse:
    touch_rate_limit_request(request)
    items, total = await service.list(
        session,
        source_system_id=source_system_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return IngestionRunListResponse(
        items=[IngestionRunRead.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/ingestion-runs",
    response_model=IngestionRunRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def create_ingestion_run(
    request: Request,
    payload: IngestionRunCreate,
    session: AsyncSession = Depends(get_async_session),
) -> IngestionRunRead:
    touch_rate_limit_request(request)
    try:
        item = await service.create(session, payload)
    except SourceSystemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source system '{payload.source_system_id}' was not found",
        ) from exc

    return IngestionRunRead.model_validate(item)
