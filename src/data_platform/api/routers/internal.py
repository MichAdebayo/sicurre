from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from core.rate_limit import limiter, touch_rate_limit_request
from core.security import require_internal_key
from db.models.lineage import DataRawRecord, DataSourceSystem

router = APIRouter(prefix="/internal", tags=["internal"])

_PHISHTANK_SOURCE_NAME = "phishtank-online-valid"


@router.get("/phishtank/snapshot")
@limiter.limit("10/minute")
async def get_phishtank_snapshot(
    request: Request,
    since: datetime | None = Query(
        default=None,
        description="ISO 8601 timestamp — only return URLs extracted after this time",
    ),
    _: None = Depends(require_internal_key),
    session: AsyncSession = Depends(get_async_session),
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
