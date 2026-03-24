from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sicurre_api.core.database import get_async_session
from sicurre_api.core.rate_limit import limiter, touch_rate_limit_request
from sicurre_api.domains.data_platform.repositories import (
    NormalizedMessageNotFoundError,
)
from sicurre_api.domains.data_platform.schemas import AnnotationCreate, AnnotationRead
from sicurre_api.domains.data_platform.services import AnnotationService


router = APIRouter(tags=["data-annotations"])
service = AnnotationService()


@router.post(
    "/annotations", response_model=AnnotationRead, status_code=status.HTTP_201_CREATED
)
@limiter.limit("30/minute")
async def create_annotation(
    request: Request,
    payload: AnnotationCreate,
    session: AsyncSession = Depends(get_async_session),
) -> AnnotationRead:
    touch_rate_limit_request(request)
    try:
        item = await service.create(session, payload)
    except NormalizedMessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Normalized message not found"
        ) from exc
    return AnnotationRead.model_validate(item)
