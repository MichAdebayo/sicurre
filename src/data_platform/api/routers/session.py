"""The signed-in member: session payload and profile update."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.config import get_settings
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import AuthSessionResponse
from data_platform.api.workspace_scope import (
    workspace_has_cloudflare_integration,
    workspace_threat_count,
)
from db.runtime import execute_runtime_query

router = APIRouter(tags=["app-ui-flows"])


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)


async def _session_payload(user: AuthUser) -> dict:
    threat_count = await workspace_threat_count(user.workspace_id)
    has_integration = await workspace_has_cloudflare_integration(user.workspace_id)
    settings = get_settings()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "workspace_name": user.workspace_name,
        "is_platform_admin": user.is_platform_admin,
        "has_cloudflare_integration": has_integration,
        "threat_count": threat_count,
        "onboarding_required": not has_integration and threat_count == 0,
        "sla_latency_ms": settings.sla_latency_ms,
    }


@router.get("/v1/auth/session", response_model=AuthSessionResponse)
async def get_session(current_user: AuthUser = Depends(get_current_user)) -> dict:
    return await _session_payload(current_user)


@router.patch("/v1/auth/profile", response_model=AuthSessionResponse)
async def patch_profile(
    payload: UpdateProfileRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    now = datetime.utcnow().isoformat() + "Z"
    await execute_runtime_query(
        'UPDATE "user" SET name = ?, "updatedAt" = ? WHERE id = ?',
        (payload.display_name.strip(), now, current_user.id),
    )
    await execute_runtime_query(
        "UPDATE app_workspace_membership SET display_name = ?, updated_at = ? WHERE auth_user_id = ?",
        (payload.display_name.strip(), now, current_user.id),
    )
    refreshed = AuthUser(
        id=current_user.id,
        email=current_user.email,
        display_name=payload.display_name.strip(),
        role=current_user.role,
        workspace_id=current_user.workspace_id,
        workspace_name=current_user.workspace_name,
        is_platform_admin=current_user.is_platform_admin,
    )
    return await _session_payload(refreshed)
