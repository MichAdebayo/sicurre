"""Erase one member's account: Cloudflare first, then the workspace, then the identity."""

from __future__ import annotations

from fastapi import HTTPException, status

from core.config import get_settings
from data_platform.api.auth import AuthUser
from data_platform.api.routers.integrations import TeardownRequest, teardown_cloudflare
from data_platform.services.quarantine_storage import build_quarantine_store
from db.runtime import execute_runtime_query

# Every table holding rows for one workspace, dependants before the tables they
# reference. The membership row carries the only foreign key, to app_workspace.
WORKSPACE_TABLES = (
    "app_alert_read",
    "app_alert_history",
    "app_alert_preference",
    "app_security_rule",
    "app_quarantine_item",
    "app_domain_shield_history",
    "app_domain_shield_status",
    "app_dmarc_report_summary",
    "app_feedback",
    "app_reported_email",
    "app_support_request",
    "app_inference_event",
    "app_cloudflare_config",
    "cloudflare_integration",
    "app_workspace_membership",
)


async def _drop_stored_quarantine_copies(workspace_id: str) -> None:
    """Delete every stored raw copy before its row goes, so no message outlives the account.

    Deleting the rows alone left the copies in storage until the 14-day lifecycle
    expired them. A storage failure stops the erasure before any row is deleted:
    the rows still point at the copies, and the member can retry.
    """
    rows = await execute_runtime_query(
        "SELECT raw_storage_uri FROM app_quarantine_item WHERE workspace_id = ? "
        "AND raw_storage_uri IS NOT NULL AND raw_storage_uri <> ''",
        (workspace_id,),
    )
    if not rows:
        return
    store = build_quarantine_store(get_settings())
    try:
        for row in rows:
            await store.delete(str(row["raw_storage_uri"]))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Quarantine storage is temporarily unavailable; the account was not deleted",
        ) from exc


async def erase_account(user: AuthUser) -> None:
    """Tear every connected domain down, delete the workspace rows, then the Better Auth rows.

    Refused (409) while a domain is still provisioning. A Cloudflare refusal
    propagates before any row is deleted, so the member keeps a working
    account and can retry. A user without a workspace loses only the identity.
    """
    email = user.email.strip().lower()
    if user.workspace_id:
        integrations = await execute_runtime_query(
            "SELECT id, status FROM cloudflare_integration WHERE workspace_id = ? "
            "ORDER BY created_at DESC",
            (user.workspace_id,),
        )
        if any(row["status"] == "provisioning" for row in integrations):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A domain is still being connected; wait for it to complete "
                "before deleting the account",
            )
        for row in integrations:
            await teardown_cloudflare(TeardownRequest(integration_id=str(row["id"])), user)
        await _drop_stored_quarantine_copies(user.workspace_id)
        for table in WORKSPACE_TABLES:
            await execute_runtime_query(
                f"DELETE FROM {table} WHERE workspace_id = ?", (user.workspace_id,)
            )
        await execute_runtime_query("DELETE FROM app_workspace WHERE id = ?", (user.workspace_id,))
    await execute_runtime_query('DELETE FROM "session" WHERE "userId" = ?', (user.id,))
    await execute_runtime_query('DELETE FROM "account" WHERE "userId" = ?', (user.id,))
    await execute_runtime_query('DELETE FROM "verification" WHERE identifier = ?', (email,))
    await execute_runtime_query('DELETE FROM "user" WHERE id = ?', (user.id,))
