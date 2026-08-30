"""Refresh every active domain shield on a bounded schedule."""

from __future__ import annotations

import asyncio
import logging

from data_platform.api.auth import AuthUser, async_query
from data_platform.api.routers.app_routes import check_domain_shield_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Refresh active integrations and fail after attempting every domain."""
    rows = await async_query(
        "SELECT DISTINCT i.workspace_id, lower(i.zone_name) AS domain, "
        "m.auth_user_id, m.email, m.display_name, m.role, w.name AS workspace_name "
        "FROM cloudflare_integration i "
        "JOIN app_workspace_membership m ON m.workspace_id = i.workspace_id "
        "AND lower(m.email) = lower(i.user_email) "
        "JOIN app_workspace w ON w.id = i.workspace_id "
        "WHERE i.status = 'active'"
    )
    failures = 0
    for row in rows:
        user = AuthUser(
            id=str(row["auth_user_id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
            workspace_id=str(row["workspace_id"]),
            workspace_name=str(row["workspace_name"]),
            is_platform_admin=False,
        )
        try:
            await check_domain_shield_status(
                domain=str(row["domain"]),
                refresh=True,
                current_user=user,
            )
        except Exception:
            failures += 1
            logger.exception("Domain Shield refresh failed for %s", row["domain"])
    logger.info("Domain Shield refresh complete: domains=%d failures=%d", len(rows), failures)
    if failures:
        raise RuntimeError(f"Domain Shield refresh failed for {failures} domain(s)")


if __name__ == "__main__":
    asyncio.run(main())
