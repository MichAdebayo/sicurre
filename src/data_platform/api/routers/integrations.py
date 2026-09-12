"""Connect a customer domain to Sicurre through Cloudflare, and disconnect it.

- ``POST /v1/integrations/cloudflare/setup``: provision Email Routing, the
  Worker, the catch-all rule and the consented DNS records.
- ``GET /v1/integrations/cloudflare/status``: the workspace's most recent
  integration record.
- ``DELETE /v1/integrations/cloudflare``: tear the integration down and
  withdraw Sicurre's DMARC reporting address.
- ``GET /v1/integrations/cloudflare/list``: the workspace's connected domains.

The Worker-facing scan routes live in ``email_scan``; the domain preview,
token check and stored token in ``cloudflare_account``; the record merges in
``services.dns_records``; the background provisioning in
``services.cloudflare_onboarding`` and the DNS sync in
``services.domain_shield_sync``.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, Field

from core.config import get_settings
from core.rate_limit import limiter
from core.secret_cipher import decrypt_secret
from data_platform.api.auth import AuthUser, ensure_runtime_tables, get_current_user
from data_platform.api.schemas.app_responses import (
    CloudflareIntegrationResponse,
)
from data_platform.api.schemas.integration_responses import (
    CloudflareSetupResponse,
    CloudflareTeardownResponse,
)
from data_platform.services.cloudflare_onboarding import provision_connected_domain
from data_platform.services.cloudflare_provisioner import (
    CloudflareAPIError,
    CloudflareProvisioner,
    encrypt_provider_token,
)
from data_platform.services.dns_records import (
    read_dns_state,
    withdraw_dmarc_reporting,
)
from data_platform.services.domain_shield_sync import sync_domain_shield_dns
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations"])

# --------------------------------------------------------------------------- Database helpers


async def _async_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return await execute_runtime_query(sql, params)


def _ensure_tables() -> None:
    """Create application tables for local development only."""
    ensure_runtime_tables()


# --------------------------------------------------------------------------- Request schemas


class CloudflareSetupRequest(BaseModel):
    cf_api_token: str | None = Field(
        default=None,
        description="Cloudflare API token with DNS + Workers + Email Routing write access",
    )
    zone_name: str = Field(..., description="Domain to protect, e.g. vinse.app")
    destination_email: str = Field(..., description="Where clean mail is forwarded after scanning")
    # Default off: rewriting SPF or DMARC is a separate consent from mail
    # interception, so the caller must opt in to each.
    fix_spf: bool = False
    fix_dmarc: bool = False


class TeardownRequest(BaseModel):
    integration_id: str | None = Field(
        default=None, description="Specific connected-domain integration to remove"
    )
    cf_api_token: str | None = Field(
        default=None, description="Optional override for the stored Cloudflare API token"
    )


# --------------------------------------------------------------------------- Connecting a domain


async def _resolve_api_token(payload: CloudflareSetupRequest, workspace_id: str) -> str:
    """The token to use: the one in the request, else the workspace's stored one.

    Raises 400 when neither exists.
    """
    api_token = payload.cf_api_token
    if not api_token:
        token_rows = await _async_query(
            "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
            (workspace_id,),
        )
        if token_rows and token_rows[0].get("api_token"):
            settings = get_settings()
            api_token = decrypt_secret(
                token_rows[0]["api_token"],
                configured_key=settings.secret_encryption_key,
                environment=settings.environment,
            )
    if not api_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cloudflare API token is not configured",
        )
    return api_token


async def _forget_failed_local_attempt(existing: list[dict[str, Any]], workspace_id: str) -> list:
    """Drop an ``error`` row that never reached Cloudflare, so the zone can be retried."""
    if not existing:
        return existing
    failed_row = existing[0]
    has_remote_resources = all(
        failed_row.get(field) for field in ("zone_id", "account_id", "worker_name")
    )
    if failed_row.get("status") == "error" and not has_remote_resources:
        await _async_query(
            "DELETE FROM cloudflare_integration WHERE id = ? AND workspace_id = ?",
            (failed_row["id"], workspace_id),
        )
        return []
    return existing


async def _resync_connected_domain(
    *,
    row: dict[str, Any],
    payload: CloudflareSetupRequest,
    api_token: str,
    workspace_id: str,
    scan_url: str,
) -> dict[str, Any]:
    """Re-apply the consented DNS fixes and redeploy the Worker of a connected zone.

    Raises 409 while a provisioning is still running and 502 when Cloudflare
    refuses the DNS or the Worker update; the refusal is stored on the row.
    """
    if row["status"] == "provisioning":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An auto-configuration for {payload.zone_name} is already running in the background. Please wait.",
        )

    now = datetime.now(timezone.utc).isoformat()
    try:
        provisioner = CloudflareProvisioner(api_token=api_token)
        dns_sync_result = await sync_domain_shield_dns(
            provisioner=provisioner,
            workspace_id=workspace_id,
            zone_name=payload.zone_name,
            fix_spf=payload.fix_spf,
            fix_dmarc=payload.fix_dmarc,
        )
    except CloudflareAPIError as exc:
        await _async_query(
            "UPDATE cloudflare_integration SET error_message=?, api_token=?, updated_at=? WHERE id=?",
            (str(exc)[:500], encrypt_provider_token(api_token), now, row["id"]),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cloudflare DNS update failed: {exc}",
        ) from exc

    worker_update_result: dict[str, Any] | None = None
    if row.get("account_id") and row.get("worker_name") and row.get("destination_email"):
        try:
            shared_secret = secrets.token_urlsafe(40)
            shared_secret_hash = hashlib.sha256(shared_secret.encode()).hexdigest()
            await provisioner.deploy_email_worker(
                account_id=row["account_id"],
                worker_name=row["worker_name"],
                scan_url=scan_url,
                shared_secret=shared_secret,
                forward_to=row["destination_email"],
            )
            await _async_query(
                """
                UPDATE cloudflare_integration
                SET shared_secret_hash=?, api_token=?, error_message=NULL, updated_at=?
                WHERE id=?
                """,
                (
                    shared_secret_hash,
                    encrypt_provider_token(api_token),
                    now,
                    row["id"],
                ),
            )
            worker_update_result = {
                "updated": True,
                "scan_url": scan_url,
                "worker_name": row["worker_name"],
            }
        except CloudflareAPIError as exc:
            await _async_query(
                "UPDATE cloudflare_integration SET error_message=?, api_token=?, updated_at=? WHERE id=?",
                (
                    str(exc)[:500],
                    encrypt_provider_token(api_token),
                    now,
                    row["id"],
                ),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Cloudflare Worker update failed: {exc}",
            ) from exc

    await _async_query(
        """
        UPDATE cloudflare_integration
        SET api_token=?, error_message=NULL, updated_at=?
        WHERE id=?
        """,
        (encrypt_provider_token(api_token), now, row["id"]),
    )
    await _store_workspace_token(workspace_id, api_token, now)
    await _async_query(
        """
        INSERT INTO app_alert_history (
            id, workspace_id, domain, event_type, action_page,
            title, message, is_dismissed, created_at
        ) VALUES (?, ?, ?, 'cloudflare_sync', NULL, ?, ?, 0, ?)
        """,
        (
            str(uuid4()),
            workspace_id,
            payload.zone_name.lower(),
            "Configuration DNS appliquée",
            f"{payload.zone_name} est synchronisé avec Cloudflare.",
            now,
        ),
    )
    return {
        "integration_id": row["id"],
        "status": row["status"],
        "zone_name": payload.zone_name,
        "destination_email": row["destination_email"],
        "dns_sync": dns_sync_result,
        "worker_update": worker_update_result,
        "message": "Domain Shield DNS configuration applied.",
    }


async def _store_workspace_token(workspace_id: str, api_token: str, now: str) -> None:
    """Keep the workspace's token so later setups and teardowns need no re-entry."""
    await _async_query(
        """
        INSERT INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(workspace_id) DO UPDATE SET
            api_token=excluded.api_token, updated_at=excluded.updated_at
        """,
        (workspace_id, encrypt_provider_token(api_token), now, now),
    )


async def _start_provisioning(
    *,
    payload: CloudflareSetupRequest,
    api_token: str,
    current_user: AuthUser,
    scan_url: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Record a ``provisioning`` row, apply the consented DNS fixes, queue the gateway.

    The DNS fixes run before the response so a refused token fails fast with
    502 and the row is marked ``error``; the gateway itself is provisioned in
    the background and the UI polls the status route.
    """
    integration_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await _async_query(
        """
        INSERT INTO cloudflare_integration
            (id, user_email, workspace_id, workspace_member_user_id, zone_id, zone_name, account_id, worker_name, rule_id,
             destination_email, api_token, shared_secret_hash, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            integration_id,
            current_user.email,
            current_user.workspace_id,
            current_user.id,
            "",
            payload.zone_name,
            "",
            "",
            "unknown",
            str(payload.destination_email),
            encrypt_provider_token(api_token),
            "",
            "provisioning",
            now,
            now,
        ),
    )
    await _store_workspace_token(current_user.workspace_id, api_token, now)

    try:
        dns_sync_result = await sync_domain_shield_dns(
            provisioner=CloudflareProvisioner(api_token=api_token),
            workspace_id=current_user.workspace_id,
            zone_name=payload.zone_name,
            fix_spf=payload.fix_spf,
            fix_dmarc=payload.fix_dmarc,
        )
    except CloudflareAPIError as exc:
        await _async_query(
            "UPDATE cloudflare_integration SET status='error', error_message=?, updated_at=? WHERE id=?",
            (str(exc)[:500], datetime.now(timezone.utc).isoformat(), integration_id),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cloudflare DNS update failed: {exc}",
        ) from exc

    background_tasks.add_task(
        provision_connected_domain,
        api_token=api_token,
        integration_id=integration_id,
        workspace_id=current_user.workspace_id,
        zone_name=payload.zone_name,
        destination_email=str(payload.destination_email),
        scan_url=scan_url,
        fix_spf=payload.fix_spf,
        fix_dmarc=payload.fix_dmarc,
    )
    return {
        "integration_id": integration_id,
        "status": "provisioning",
        "zone_name": payload.zone_name,
        "destination_email": str(payload.destination_email),
        "dns_sync": dns_sync_result,
        "message": "Provisioning started. Poll /v1/integrations/cloudflare/status to track progress.",
    }


@router.post(
    "/v1/integrations/cloudflare/setup",
    status_code=status.HTTP_201_CREATED,
    response_model=CloudflareSetupResponse,
    response_model_exclude_unset=True,
)
@limiter.limit("10/hour")
async def setup_cloudflare(
    payload: CloudflareSetupRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Connect ``zone_name`` to Sicurre, or re-apply the consented fixes if it already is.

    Returns 201 with the integration id and the DNS result. Raises 400 without
    a token, 409 while a provisioning is running, 502 when Cloudflare refuses.
    """
    _ensure_tables()
    settings = get_settings()
    public_api_url = (
        settings.public_api_url.rstrip("/")
        if settings.public_api_url
        else str(request.base_url).rstrip("/")
    )
    scan_url = f"{public_api_url}/v1/email/scan"

    existing = await _async_query(
        "SELECT * FROM cloudflare_integration WHERE workspace_id = ? AND zone_name = ? LIMIT 1",
        (current_user.workspace_id, payload.zone_name),
    )
    api_token = await _resolve_api_token(payload, current_user.workspace_id)
    existing = await _forget_failed_local_attempt(existing, current_user.workspace_id)
    if existing:
        return await _resync_connected_domain(
            row=existing[0],
            payload=payload,
            api_token=api_token,
            workspace_id=current_user.workspace_id,
            scan_url=scan_url,
        )
    return await _start_provisioning(
        payload=payload,
        api_token=api_token,
        current_user=current_user,
        scan_url=scan_url,
        background_tasks=background_tasks,
    )


# --------------------------------------------------------------------------- Integration status


@router.get(
    "/v1/integrations/cloudflare/status",
    response_model=CloudflareIntegrationResponse,
    response_model_exclude_unset=True,
)
async def cloudflare_status(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the most recent integration record for a user."""
    _ensure_tables()
    rows = await _async_query(
        "SELECT * FROM cloudflare_integration WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 1",
        (current_user.workspace_id,),
    )
    if not rows:
        return {"status": "not_configured"}
    row = rows[0]
    status = row["status"]
    return {
        "id": row["id"],
        "user_email": row["user_email"],
        "zone_name": row["zone_name"],
        "destination_email": row["destination_email"],
        "worker_name": row["worker_name"],
        "status": status,
        "token_configured": bool(row.get("api_token")),
        "error_message": row.get("error_message") if status == "error" else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# --------------------------------------------------------------------------- Disconnecting a domain


@router.delete(
    "/v1/integrations/cloudflare",
    response_model=CloudflareTeardownResponse,
)
async def teardown_cloudflare(
    payload: TeardownRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove the Cloudflare Worker and routing rule then delete the DB record."""
    _ensure_tables()
    if payload.integration_id:
        rows = await _async_query(
            "SELECT * FROM cloudflare_integration WHERE id = ? AND workspace_id = ? LIMIT 1",
            (payload.integration_id, current_user.workspace_id),
        )
    else:
        rows = await _async_query(
            "SELECT * FROM cloudflare_integration WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 1",
            (current_user.workspace_id,),
        )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No integration found")

    row = rows[0]
    if row["status"] in ("provisioning",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provisioning in progress; wait for it to complete before tearing down",
        )

    has_remote_resources = all(row.get(field) for field in ("zone_id", "account_id", "worker_name"))
    local_failed_attempt = row["status"] == "error" and not has_remote_resources
    # False only when we tried to withdraw our reporting address and could not,
    # which is the one case an operator has to finish by hand.
    dmarc_reporting_withdrawn = True
    if has_remote_resources:
        settings = get_settings()
        encrypted_token = payload.cf_api_token or row.get("api_token")
        if not encrypted_token:
            token_rows = await _async_query(
                "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
                (current_user.workspace_id,),
            )
            encrypted_token = token_rows[0].get("api_token") if token_rows else None
        if not encrypted_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cloudflare API token is not configured",
            )
        api_token = (
            encrypted_token
            if payload.cf_api_token
            else decrypt_secret(
                str(encrypted_token),
                configured_key=settings.secret_encryption_key,
                environment=settings.environment,
            )
        )

        try:
            provisioner = CloudflareProvisioner(api_token=api_token)
            await provisioner.teardown(
                zone_id=row["zone_id"],
                account_id=row["account_id"],
                worker_name=row["worker_name"],
                rule_id=row.get("rule_id") or "unknown",
            )
        except CloudflareAPIError as exc:
            logger.warning("Cloudflare teardown had errors: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Cloudflare could not remove the routing resources: {exc}",
            ) from exc

        # Withdraw Sicurre's DMARC reporting address. The Worker and rule are
        # already gone, so a DNS failure here is reported rather than raised.
        try:
            _, _, existing_dmarc = read_dns_state(
                await provisioner.get_dns_records(row["zone_id"]), row["zone_name"]
            )
            withdrawn = withdraw_dmarc_reporting(existing_dmarc)
            if withdrawn is not None:
                await provisioner.deploy_dns_record(
                    zone_id=row["zone_id"],
                    rec_type="TXT",
                    name=f"_dmarc.{row['zone_name']}",
                    content=withdrawn,
                    match_prefix="v=DMARC1",
                )
                logger.info("Withdrew Sicurre DMARC reporting from %s", row["zone_name"])
        except Exception as exc:
            # Deliberately broad: the destructive half of the teardown has
            # already succeeded, so nothing here may raise past this point.
            dmarc_reporting_withdrawn = False
            logger.warning(
                "Could not withdraw Sicurre DMARC reporting from %s; "
                "the domain will keep sending aggregate reports until it is "
                "removed by hand: %s",
                row["zone_name"],
                exc,
            )

    await _async_query(
        "DELETE FROM cloudflare_integration WHERE id = ?",
        (row["id"],),
    )

    # Check if any remaining connected domains exist for this workspace
    remaining = await _async_query(
        "SELECT id FROM cloudflare_integration WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,),
    )
    if not remaining and not local_failed_attempt:
        # Parent domain removed: purge orphaned workspace tokens and shield cache
        await _async_query(
            "DELETE FROM app_cloudflare_config WHERE workspace_id = ?",
            (current_user.workspace_id,),
        )
        await _async_query(
            # Scoped to this workspace. `OR domain = ?` deleted the status for
            # that domain in every workspace holding it, so one customer
            # disconnecting wiped another customer's shield.
            "DELETE FROM app_domain_shield_status WHERE workspace_id = ?",
            (current_user.workspace_id,),
        )

    return {
        "status": "removed",
        "zone_name": row["zone_name"],
        "dmarc_reporting_withdrawn": dmarc_reporting_withdrawn,
    }


# --------------------------------------------------------------------------- Connected domains


@router.get(
    "/v1/integrations/cloudflare/list",
    response_model=list[CloudflareIntegrationResponse],
)
async def list_cloudflare_integrations(current_user: AuthUser = Depends(get_current_user)):
    rows = await _async_query(
        "SELECT * FROM cloudflare_integration WHERE workspace_id = ? ORDER BY created_at DESC",
        (current_user.workspace_id,),
    )
    return [
        {
            "id": r["id"],
            "user_email": r["user_email"],
            "zone_name": r["zone_name"],
            "destination_email": r["destination_email"],
            "worker_name": r["worker_name"],
            "status": r["status"],
            "token_configured": bool(r.get("api_token")),
            "error_message": r.get("error_message") if r["status"] == "error" else None,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
