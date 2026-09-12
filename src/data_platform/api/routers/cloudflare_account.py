"""The workspace's Cloudflare account: domain preview, token check, stored token.

- ``POST /v1/integrations/cloudflare/preview``: describe a domain from public
  DNS before any token exists.
- ``POST /v1/integrations/cloudflare/verify-token``: read the zone with the
  customer's token and return the DNS plan without writing anything.
- ``GET``/``POST``/``DELETE /v1/integrations/cloudflare/token``: the
  workspace's encrypted Cloudflare token.

Connecting and disconnecting a domain live in ``integrations``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.domain_preview import normalize_zone, read_public_dns
from core.rate_limit import limiter
from data_platform.api.auth import AuthUser, ensure_runtime_tables, get_current_user
from data_platform.api.schemas.app_responses import StatusResponse
from data_platform.api.schemas.integration_responses import (
    CloudflareDomainPreviewResponse,
    CloudflareTokenStatusResponse,
    CloudflareTokenVerificationResponse,
)
from data_platform.services.cloudflare_provisioner import (
    CloudflareAPIError,
    CloudflareProvisioner,
    encrypt_provider_token,
)
from data_platform.services.dns_records import (
    SICURRE_DMARC_MAILBOX,
    clean_str,
    merge_dmarc,
    merge_spf,
    planned_change,
    read_dns_state,
)
from db.runtime import execute_runtime_query

router = APIRouter(tags=["integrations"])


async def _async_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return await execute_runtime_query(sql, params)


class TokenVerifyRequest(BaseModel):
    cf_api_token: str
    zone_name: str


@router.post(
    "/v1/integrations/cloudflare/verify-token",
    response_model=CloudflareTokenVerificationResponse,
    response_model_exclude_unset=True,
)
async def verify_cloudflare_token(
    payload: TokenVerifyRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Lightweight check: verify the token is valid and can see the requested zone.
    Called by the UI before the actual setup to give early feedback.
    """
    try:
        provisioner = CloudflareProvisioner(api_token=payload.cf_api_token)
        token_ok = await provisioner.verify_token()
        if not token_ok:
            return {"valid": False, "error": "Token verification failed"}
        zone_id, _ = await provisioner.get_zone(payload.zone_name)
        # Read the zone and work out what connecting would actually change, so
        # the customer can be shown it before they press the button rather than
        # after. This is the same read provisioning does; nothing is written.
        spf, dkim, dmarc = read_dns_state(
            await provisioner.get_dns_records(zone_id), payload.zone_name
        )
        return {
            "valid": True,
            "zone_id": zone_id,
            "plan": {
                "spf": planned_change(spf, merge_spf(spf)),
                "dmarc": planned_change(dmarc, merge_dmarc(dmarc)),
                "dkim_present": bool(dkim),
            },
        }
    except CloudflareAPIError as exc:
        return {"valid": False, "error": str(exc)}


class DomainPreviewRequest(BaseModel):
    zone_name: str = Field(..., min_length=3, max_length=253)


@router.post(
    "/v1/integrations/cloudflare/preview",
    response_model=CloudflareDomainPreviewResponse,
    response_model_exclude_unset=True,
)
@limiter.limit("30/minute")
async def preview_cloudflare_domain(
    payload: DomainPreviewRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Describe a domain from public DNS, before the customer creates a token.

    Reports whether the zone is on Cloudflare, who receives its mail, and
    what connecting would add or modify. Reads only; needs no credentials.
    """
    zone = normalize_zone(payload.zone_name)
    if zone is None:
        raise HTTPException(status_code=422, detail="zone_name must be a hostname")
    snapshot = await read_public_dns(zone)
    if not snapshot.resolvable:
        return {
            "zone_name": zone,
            "resolvable": False,
            "on_cloudflare": False,
            "mail_provider": "none",
        }
    dmarc = clean_str(snapshot.dmarc)
    policy = (
        "reject" if "p=reject" in dmarc else "quarantine" if "p=quarantine" in dmarc else "none"
    )
    return {
        "zone_name": zone,
        "resolvable": True,
        "on_cloudflare": snapshot.on_cloudflare,
        "nameservers": snapshot.nameservers,
        "mail_provider": snapshot.mail_provider,
        "mx_hosts": snapshot.mx_hosts,
        "plan": {
            "spf": planned_change(snapshot.spf, merge_spf(snapshot.spf)),
            "dmarc": planned_change(snapshot.dmarc, merge_dmarc(snapshot.dmarc)),
            "dkim_present": snapshot.dkim_present,
        },
        "dmarc_policy": policy if dmarc else None,
        "dmarc_reporting": SICURRE_DMARC_MAILBOX in dmarc.lower(),
    }


class CloudflareTokenSaveRequest(BaseModel):
    cf_api_token: str = Field(..., description="Cloudflare API token to store")


@router.get(
    "/v1/integrations/cloudflare/token",
    response_model=CloudflareTokenStatusResponse,
)
async def get_workspace_cloudflare_token(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the stored Cloudflare API token for the current workspace if an active domain is connected."""
    ensure_runtime_tables()

    # Require at least one connected domain in cloudflare_integration
    integ_rows = await _async_query(
        "SELECT api_token FROM cloudflare_integration WHERE workspace_id = ? AND api_token IS NOT NULL AND api_token != '' ORDER BY created_at DESC LIMIT 1",
        (current_user.workspace_id,),
    )
    if not integ_rows:
        # Parent domain missing: purge orphaned token config if any
        await _async_query(
            "DELETE FROM app_cloudflare_config WHERE workspace_id = ?",
            (current_user.workspace_id,),
        )
        return {"configured": False}

    rows = await _async_query(
        "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,),
    )
    if rows and rows[0]["api_token"]:
        return {"configured": True}

    return {"configured": bool(integ_rows[0]["api_token"])}


@router.post("/v1/integrations/cloudflare/token", response_model=StatusResponse)
async def save_workspace_cloudflare_token(
    payload: CloudflareTokenSaveRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Save or overwrite the stored Cloudflare API token for the current workspace."""
    # Lightweight check: verify token works
    try:
        provisioner = CloudflareProvisioner(api_token=payload.cf_api_token)
        token_ok = await provisioner.verify_token()
        if not token_ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token verification failed on Cloudflare API",
            )
    except CloudflareAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token verification failed: {str(exc)}",
        ) from exc

    ts = datetime.now(timezone.utc).isoformat()
    await _async_query(
        """
        INSERT INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(workspace_id) DO UPDATE SET
            api_token=excluded.api_token, updated_at=excluded.updated_at
        """,
        (
            current_user.workspace_id,
            encrypt_provider_token(payload.cf_api_token),
            ts,
            ts,
        ),
    )
    return {"status": "saved"}


@router.delete("/v1/integrations/cloudflare/token", response_model=StatusResponse)
async def delete_workspace_cloudflare_token(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete the stored Cloudflare API token and all connected integrations for the current workspace."""
    await _async_query(
        "DELETE FROM app_cloudflare_config WHERE workspace_id = ?",
        (current_user.workspace_id,),
    )
    await _async_query(
        "DELETE FROM cloudflare_integration WHERE workspace_id = ?",
        (current_user.workspace_id,),
    )
    await _async_query(
        "DELETE FROM app_domain_shield_status WHERE workspace_id = ?",
        (current_user.workspace_id,),
    )
    return {"status": "deleted"}
