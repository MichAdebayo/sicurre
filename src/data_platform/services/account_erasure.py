"""Erase one member's account: Cloudflare first, then the workspace, then the identity."""

from __future__ import annotations

import logging

from fastapi import HTTPException, status

from core.config import get_settings
from data_platform.api.auth import AuthUser
from data_platform.api.routers.integrations import TeardownRequest, teardown_cloudflare
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)

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


def platform_zone() -> str:
    """Return the zone Sicurre receives its own mail on: the domain of the report mailbox.

    The platform's catch-all and a customer connection of that zone share one
    Worker, whose name derives from the zone id. Tearing the zone down for a
    customer would stop every inbound mail to the platform.
    """
    return get_settings().reported_email_address.strip().lower().rsplit("@", 1)[-1]


async def erase_account(user: AuthUser) -> None:
    """Tear every connected domain down, delete the workspace rows, then the Better Auth rows.

    Refused (409) while a domain is still provisioning. A Cloudflare refusal
    propagates before any row is deleted, so the member keeps a working
    account and can retry. The platform's own zone is never torn down: its
    rows go, its Worker and routing rule keep serving the platform. A user
    without a workspace loses only the identity.
    """
    email = user.email.strip().lower()
    if user.workspace_id:
        integrations = await execute_runtime_query(
            "SELECT id, status, zone_name FROM cloudflare_integration WHERE workspace_id = ? "
            "ORDER BY created_at DESC",
            (user.workspace_id,),
        )
        if any(row["status"] == "provisioning" for row in integrations):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A domain is still being connected; wait for it to complete "
                "before deleting the account",
            )
        shared_zone = platform_zone()
        for row in integrations:
            if str(row.get("zone_name") or "").strip().lower() == shared_zone:
                logger.warning(
                    "Kept the Cloudflare resources of %s while erasing %s: "
                    "the platform receives its own mail through them",
                    shared_zone,
                    email,
                )
                continue
            await teardown_cloudflare(TeardownRequest(integration_id=str(row["id"])), user)
        for table in WORKSPACE_TABLES:
            await execute_runtime_query(
                f"DELETE FROM {table} WHERE workspace_id = ?", (user.workspace_id,)
            )
        await execute_runtime_query("DELETE FROM app_workspace WHERE id = ?", (user.workspace_id,))
    await execute_runtime_query('DELETE FROM "session" WHERE "userId" = ?', (user.id,))
    await execute_runtime_query('DELETE FROM "account" WHERE "userId" = ?', (user.id,))
    await execute_runtime_query('DELETE FROM "verification" WHERE identifier = ?', (email,))
    await execute_runtime_query('DELETE FROM "user" WHERE id = ?', (user.id,))
