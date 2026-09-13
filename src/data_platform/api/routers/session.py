"""The signed-in member: session payload, profile update and account erasure."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.config import get_settings
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import AuthSessionResponse, StatusResponse
from data_platform.api.workspace_scope import (
    workspace_default_domain,
    workspace_has_cloudflare_integration,
    workspace_threat_count,
)
from data_platform.services.account_erasure import erase_account
from db.runtime import execute_runtime_query

router = APIRouter(tags=["app-ui-flows"])


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)


class DeleteAccountRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
        description="The account email, typed again by the member as confirmation",
    )


async def _session_payload(user: AuthUser) -> dict:
    # Independent lookups, issued together rather than one after another.
    threat_count, has_integration, default_domain = await asyncio.gather(
        workspace_threat_count(user.workspace_id),
        workspace_has_cloudflare_integration(user.workspace_id),
        workspace_default_domain(user.workspace_id),
    )
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
        "default_domain": default_domain,
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


@router.delete("/v1/auth/account", response_model=StatusResponse)
async def delete_account(
    payload: DeleteAccountRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    """Erase the member's own account: connected domains are torn down on Cloudflare first, then every workspace row and the identity are deleted in one pass.

    Refused when the typed email does not match the account, and while a domain is still provisioning. A Cloudflare refusal stops the erasure before any row is deleted, so the member keeps a working account and can retry.
    """
    if payload.email.strip().lower() != current_user.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation email does not match the account",
        )
    await erase_account(current_user)
    return {"status": "deleted"}
