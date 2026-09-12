"""Held messages: list, release to the destination mailbox, delete, whitelist."""

from __future__ import annotations

import logging
import uuid
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from core.config import get_settings
from core.secret_cipher import decrypt_secret
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import (
    QuarantineItemResponse,
    QuarantineReleaseResponse,
    QuarantineWhitelistResponse,
    StatusResponse,
)
from data_platform.api.workspace_scope import owned_domain
from data_platform.services.quarantine_delivery import (
    QuarantineDeliveryError,
    prepare_restoration_mime,
    resolve_sending_address,
    send_raw_email,
)
from data_platform.services.quarantine_retention import purge_expired_quarantine
from data_platform.services.quarantine_storage import build_quarantine_store
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["app-ui-flows"])


async def _purge_expired_quarantine(workspace_id: str):
    return await purge_expired_quarantine(
        query=execute_runtime_query,
        store=build_quarantine_store(get_settings()),
        workspace_id=workspace_id,
    )


@router.get("/v1/quarantine", response_model=list[QuarantineItemResponse])
async def list_quarantine(domain: str, current_user: AuthUser = Depends(get_current_user)):
    active_domain = await owned_domain(domain, current_user)
    await _purge_expired_quarantine(current_user.workspace_id)
    rows = await execute_runtime_query(
        "SELECT * FROM app_quarantine_item WHERE workspace_id = ? "
        "AND lower(domain) = lower(?) AND status = 'held' ORDER BY created_at DESC",
        (current_user.workspace_id, active_domain),
    )
    return [
        {
            "id": r["id"],
            "domain": active_domain,
            "message_id": r["message_id"],
            "sender": r["sender"],
            "subject": r["subject"],
            "body_text": r["body_text"],
            "safety_verdict": r["safety_verdict"],
            "composite_score": r["composite_score"],
            "status": r["status"],
            "created_at": r["created_at"],
            "expires_at": r["expires_at"],
        }
        for r in rows
    ]


@router.post(
    "/v1/quarantine/{id}/release",
    response_model=QuarantineReleaseResponse,
    response_model_exclude_unset=True,
)
async def release_quarantine_item(
    id: str,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    return await _release_quarantine_item(id=id, domain=domain, current_user=current_user)


async def _release_quarantine_item(*, id: str, domain: str, current_user: AuthUser) -> dict:
    """Release one held item with durable, idempotent delivery state."""
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT * FROM app_quarantine_item WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?) LIMIT 1",
        (id, current_user.workspace_id, active_domain),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quarantined item not found")
    item = rows[0]
    if item["status"] == "released":
        integrations = await execute_runtime_query(
            "SELECT destination_email FROM cloudflare_integration "
            "WHERE workspace_id = ? AND lower(zone_name) = lower(?) LIMIT 1",
            (current_user.workspace_id, item.get("domain") or ""),
        )
        return {
            "status": "released",
            "forwarded_to": integrations[0]["destination_email"] if integrations else "",
            "delivery_message_id": item.get("delivery_message_id"),
            "idempotent": True,
        }
    if item["status"] == "releasing":
        raise HTTPException(status_code=409, detail="Message release is already in progress")
    if item["status"] != "held":
        raise HTTPException(status_code=409, detail="Message is no longer held")
    if not item.get("raw_storage_uri"):
        raise HTTPException(
            status_code=409,
            detail="Original email content is unavailable; the message was not released",
        )

    integrations = await execute_runtime_query(
        "SELECT account_id, zone_id, zone_name, destination_email, api_token "
        "FROM cloudflare_integration WHERE workspace_id = ? AND status = 'active' "
        "AND lower(zone_name) = lower(?) LIMIT 1",
        (current_user.workspace_id, item.get("domain") or ""),
    )
    if not integrations:
        raise HTTPException(status_code=409, detail="Active Cloudflare integration required")
    integration = integrations[0]
    if not integration.get("api_token"):
        raise HTTPException(status_code=409, detail="Cloudflare token is not configured")

    claimed = await execute_runtime_query(
        "UPDATE app_quarantine_item SET status = 'releasing', last_delivery_error = NULL "
        "WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?) "
        "AND status = 'held' RETURNING id",
        (id, current_user.workspace_id, active_domain),
    )
    if not claimed:
        raise HTTPException(status_code=409, detail="Message release is already in progress")
    settings = get_settings()
    store = build_quarantine_store(settings)
    try:
        raw_mime = await store.read(str(item["raw_storage_uri"]))
        api_token = decrypt_secret(
            str(integration["api_token"]),
            configured_key=settings.secret_encryption_key,
            environment=settings.environment,
        )
        envelope_from = await resolve_sending_address(
            api_token=api_token,
            account_id=str(integration["account_id"]),
            zone_id=str(integration["zone_id"]),
            zone_name=str(integration["zone_name"]),
            recipient=str(integration["destination_email"]),
        )
        delivery_mime = prepare_restoration_mime(
            raw_mime,
            sender=envelope_from,
            recipient=str(integration["destination_email"]),
        )
        result = await send_raw_email(
            api_token=api_token,
            account_id=str(integration["account_id"]),
            envelope_from=envelope_from,
            recipient=str(integration["destination_email"]),
            raw_mime=delivery_mime,
        )
    except QuarantineDeliveryError as exc:
        await execute_runtime_query(
            "UPDATE app_quarantine_item SET status = 'held', last_delivery_error = ? "
            "WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?)",
            (str(exc)[:240], id, current_user.workspace_id, active_domain),
        )
        status_code = 403 if exc.code.endswith("permission_required") else 424
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Quarantine release failed")
        await execute_runtime_query(
            "UPDATE app_quarantine_item SET status = 'held', last_delivery_error = ? "
            "WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?)",
            ("Quarantine storage is unavailable", id, current_user.workspace_id, active_domain),
        )
        raise HTTPException(
            status_code=503,
            detail="Quarantine storage is temporarily unavailable",
        ) from exc

    delivered_at = datetime.now(timezone.utc).isoformat()
    await execute_runtime_query(
        "UPDATE app_quarantine_item SET status = 'released', delivery_message_id = ?, "
        "delivered_at = ?, last_delivery_error = NULL WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?)",
        (result.message_id, delivered_at, id, current_user.workspace_id, active_domain),
    )
    await _record_release_feedback(item=item, current_user=current_user)
    with suppress(Exception):
        await store.delete(str(item["raw_storage_uri"]))
        await execute_runtime_query(
            "UPDATE app_quarantine_item SET raw_storage_uri = NULL WHERE id = ? AND workspace_id = ? "
            "AND lower(domain) = lower(?)",
            (id, current_user.workspace_id, active_domain),
        )
    return {
        "status": "released",
        "forwarded_to": result.recipient,
        "delivery_message_id": result.message_id,
        "queued": result.queued,
        "idempotent": False,
    }


async def _record_release_feedback(*, item: dict, current_user: AuthUser) -> None:
    """Record a false-positive correction once for a released quarantine item."""
    with suppress(Exception):
        await execute_runtime_query(
            "INSERT INTO app_feedback (id, workspace_id, workspace_member_user_id, event_id, "
            "feedback_type, original_verdict, corrected_verdict, reporter_note, created_at) "
            "VALUES (?, ?, ?, ?, 'false_positive', ?, 'legitimate', ?, ?)",
            (
                str(uuid.uuid4()),
                current_user.workspace_id,
                current_user.id,
                item["message_id"],
                item["safety_verdict"],
                "Released from quarantine by the user",
                datetime.now(timezone.utc).isoformat(),
            ),
        )


@router.delete("/v1/quarantine/{id}", response_model=StatusResponse)
async def delete_quarantine_item(
    id: str,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT raw_storage_uri FROM app_quarantine_item WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?) LIMIT 1",
        (id, current_user.workspace_id, active_domain),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quarantined item not found")

    if rows[0].get("raw_storage_uri"):
        try:
            await build_quarantine_store(get_settings()).delete(str(rows[0]["raw_storage_uri"]))
        except Exception as exc:
            logger.exception("Quarantine deletion failed")
            raise HTTPException(
                status_code=503,
                detail="Quarantine storage is temporarily unavailable",
            ) from exc
    await execute_runtime_query(
        "UPDATE app_quarantine_item SET status = 'deleted', sender = '[deleted]', "
        "subject = '[deleted]', body_text = '', raw_storage_uri = NULL, "
        "raw_content_hash = NULL, raw_size_bytes = NULL, last_delivery_error = NULL "
        "WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?)",
        (id, current_user.workspace_id, active_domain),
    )
    return {"status": "deleted"}


@router.post(
    "/v1/quarantine/{id}/whitelist",
    response_model=QuarantineWhitelistResponse,
    response_model_exclude_unset=True,
)
async def release_and_whitelist_item(
    id: str,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT * FROM app_quarantine_item WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?) AND status IN ('held', 'released') LIMIT 1",
        (id, current_user.workspace_id, active_domain),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quarantined item not found")
    item = rows[0]
    result = await _release_quarantine_item(
        id=id,
        domain=active_domain,
        current_user=current_user,
    )
    sender = str(item["sender"]).strip().lower()
    existing = await execute_runtime_query(
        "SELECT id FROM app_security_rule WHERE workspace_id = ? "
        "AND lower(domain) = lower(?) AND rule_type = 'whitelist' "
        "AND lower(pattern) = ? LIMIT 1",
        (current_user.workspace_id, active_domain, sender),
    )
    if not existing:
        await execute_runtime_query(
            "INSERT INTO app_security_rule "
            "(id, workspace_id, domain, rule_type, pattern, created_at) "
            "VALUES (?, ?, ?, 'whitelist', ?, ?)",
            (
                str(uuid.uuid4()),
                current_user.workspace_id,
                active_domain,
                sender,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return {**result, "whitelisted_pattern": sender}
