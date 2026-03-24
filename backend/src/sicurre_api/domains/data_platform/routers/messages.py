from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sicurre_api.core.database import get_async_session
from sicurre_api.core.rate_limit import limiter, touch_rate_limit_request
from sicurre_api.domains.data_platform.models import NormalizedLabel, SplitName
from sicurre_api.domains.data_platform.repositories import (
    DuplicateNormalizedMessageError,
    NormalizedMessageDependencyError,
    NormalizedMessageNotFoundError,
)
from sicurre_api.domains.data_platform.schemas import (
    NormalizedMessageCreate,
    NormalizedMessageListResponse,
    NormalizedMessageRead,
    NormalizedMessageUpdate,
)
from sicurre_api.domains.data_platform.services import NormalizedMessageService


router = APIRouter(tags=["data-messages"])
service = NormalizedMessageService()


@router.get("/messages", response_model=NormalizedMessageListResponse)
@limiter.limit("60/minute")
async def list_messages(
    request: Request,
    label: NormalizedLabel | None = Query(default=None),
    language: str | None = None,
    split: SplitName | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> NormalizedMessageListResponse:
    touch_rate_limit_request(request)
    items, total = await service.list(
        session,
        label=label,
        language=language,
        split=split,
        limit=limit,
        offset=offset,
    )
    return NormalizedMessageListResponse(
        items=[NormalizedMessageRead.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/messages",
    response_model=NormalizedMessageRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def create_message(
    request: Request,
    payload: NormalizedMessageCreate,
    session: AsyncSession = Depends(get_async_session),
) -> NormalizedMessageRead:
    touch_rate_limit_request(request)
    try:
        item = await service.create(session, payload)
    except NormalizedMessageDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Raw record or processing run was not found",
        ) from exc
    except DuplicateNormalizedMessageError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Normalized message already exists",
        ) from exc

    return NormalizedMessageRead.model_validate(item)


@router.get("/messages/{id}", response_model=NormalizedMessageRead)
@limiter.limit("60/minute")
async def get_message(
    request: Request,
    id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> NormalizedMessageRead:
    touch_rate_limit_request(request)
    item = await service.get(session, id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Normalized message not found"
        )
    return NormalizedMessageRead.model_validate(item)


@router.patch("/messages/{id}", response_model=NormalizedMessageRead)
@limiter.limit("20/minute")
async def update_message(
    request: Request,
    id: UUID,
    payload: NormalizedMessageUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> NormalizedMessageRead:
    touch_rate_limit_request(request)
    try:
        item = await service.update(session, id, payload)
    except NormalizedMessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Normalized message not found"
        ) from exc

    return NormalizedMessageRead.model_validate(item)


@router.delete("/messages/{id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_message(
    request: Request,
    id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    touch_rate_limit_request(request)
    deleted = await service.delete(session, id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Normalized message not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
