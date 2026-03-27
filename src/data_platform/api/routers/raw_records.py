from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.rate_limit import limiter, touch_rate_limit_request
from data_platform.api.schemas import (
    RawRecordListResponse,
    RawRecordRead,
)
from storage.services import RawRecordService


router = APIRouter(tags=["data-raw-records"])
service = RawRecordService()


@router.get("/raw-records", response_model=RawRecordListResponse)
@limiter.limit("60/minute")
async def list_raw_records(
    request: Request,
    source_system_id: UUID | None = None,
    language: str | None = None,
    is_usable: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> RawRecordListResponse:
    touch_rate_limit_request(request)
    items, total = await service.list(
        session,
        source_system_id=source_system_id,
        language=language,
        is_usable=is_usable,
        limit=limit,
        offset=offset,
    )
    return RawRecordListResponse(
        items=[RawRecordRead.model_validate(item) for item in items], total=total
    )
