from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sicurre_api.core.database import get_async_session
from sicurre_api.core.rate_limit import limiter, touch_rate_limit_request
from sicurre_api.domains.data_platform.models import SourceType
from sicurre_api.domains.data_platform.repositories import DuplicateDataSourceError
from sicurre_api.domains.data_platform.schemas import (
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceRead,
)
from sicurre_api.domains.data_platform.services import SourceSystemService


router = APIRouter(tags=["data-sources"])
service = SourceSystemService()


@router.get("/sources", response_model=DataSourceListResponse)
@limiter.limit("60/minute")
async def list_sources(
    request: Request,
    source_type: SourceType | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> DataSourceListResponse:
    touch_rate_limit_request(request)
    items, total = await service.list(
        session,
        source_type=source_type,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return DataSourceListResponse(
        items=[DataSourceRead.model_validate(item) for item in items], total=total
    )


@router.post(
    "/sources", response_model=DataSourceRead, status_code=status.HTTP_201_CREATED
)
@limiter.limit("30/minute")
async def create_source(
    request: Request,
    payload: DataSourceCreate,
    session: AsyncSession = Depends(get_async_session),
) -> DataSourceRead:
    touch_rate_limit_request(request)
    try:
        item = await service.create(session, payload)
    except DuplicateDataSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Data source '{payload.name}' already exists",
        ) from exc

    return DataSourceRead.model_validate(item)
