"""Workspace ownership checks shared by the customer-facing routers.

A route names a domain; these confirm it belongs to the caller's workspace
before anything is read or written for it.
"""

from __future__ import annotations

from fastapi import HTTPException

from data_platform.api.auth import AuthUser
from db.runtime import execute_runtime_query


async def require_workspace_domain(domain: str, workspace_id: str) -> None:
    """Reject a domain that is not connected to the caller's workspace."""
    rows = await execute_runtime_query(
        "SELECT 1 FROM cloudflare_integration "
        "WHERE workspace_id = ? AND lower(zone_name) = lower(?) LIMIT 1",
        (workspace_id, domain),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Connected domain not found")


async def owned_domain(domain: str, current_user: AuthUser) -> str:
    normalized = domain.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Domain is required")
    await require_workspace_domain(normalized, current_user.workspace_id)
    return normalized


async def workspace_threat_count(workspace_id: str, domain: str | None = None) -> int:
    where = "workspace_id = ?"
    params: tuple[object, ...] = (workspace_id,)
    if domain:
        where += " AND lower(domain) = lower(?)"
        params += (domain,)
    rows = await execute_runtime_query(
        f"SELECT COUNT(*) AS count FROM app_inference_event WHERE {where}",
        params,
    )
    return int(rows[0]["count"]) if rows else 0


async def workspace_has_cloudflare_integration(workspace_id: str) -> bool:
    rows = await execute_runtime_query(
        "SELECT 1 AS found FROM cloudflare_integration WHERE workspace_id = ? AND status IN ('pending_verification', 'active', 'provisioning') LIMIT 1",
        (workspace_id,),
    )
    return bool(rows)
