from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.rate_limit import limiter, touch_rate_limit_request
from db.models import DatasetStatus
from db.queries import (
    DatasetNotFoundError,
    DuplicateDatasetError,
)
from data_platform.api.schemas import (
    DatasetCreate,
    DatasetItemListResponse,
    DatasetItemRead,
    DatasetListResponse,
    DatasetRead,
)
from db.services import DatasetService


router = APIRouter(tags=["data-datasets"])
service = DatasetService()


@router.get("/datasets", response_model=DatasetListResponse)
@limiter.limit("60/minute")
async def list_datasets(
    request: Request,
    status: DatasetStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> DatasetListResponse:
    touch_rate_limit_request(request)
    items, total = await service.list(
        session,
        status=status,
        limit=limit,
        offset=offset,
    )
    return DatasetListResponse(
        items=[DatasetRead.model_validate(item) for item in items], total=total
    )


@router.post(
    "/datasets", response_model=DatasetRead, status_code=status.HTTP_201_CREATED
)
@limiter.limit("30/minute")
async def create_dataset(
    request: Request,
    payload: DatasetCreate,
    session: AsyncSession = Depends(get_async_session),
) -> DatasetRead:
    touch_rate_limit_request(request)
    try:
        item = await service.create(session, payload)
    except DuplicateDatasetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset version already exists",
        ) from exc
    return DatasetRead.model_validate(item)


@router.get("/datasets/{id}/items", response_model=DatasetItemListResponse)
@limiter.limit("60/minute")
async def list_dataset_items(
    request: Request,
    id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> DatasetItemListResponse:
    touch_rate_limit_request(request)
    try:
        items, total = await service.list_items(
            session,
            id,
            limit=limit,
            offset=offset,
        )
    except DatasetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found"
        ) from exc
    return DatasetItemListResponse(
        items=[DatasetItemRead.model_validate(item) for item in items], total=total
    )
