"""Provision a newly connected domain in the background.

The setup route inserts a ``provisioning`` row and returns at once; this
runs after the response: Email Routing, the Worker, the catch-all rule, then
the consented DNS records. Every outcome is written back to the row the UI
polls.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from data_platform.services.cloudflare_provisioner import CloudflareAPIError, CloudflareProvisioner
from data_platform.services.domain_shield_sync import sync_domain_shield_dns
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)


async def provision_connected_domain(
    *,
    api_token: str,
    integration_id: str,
    workspace_id: str,
    zone_name: str,
    destination_email: str,
    scan_url: str,
    fix_spf: bool,
    fix_dmarc: bool,
) -> None:
    """Provision the Cloudflare gateway for ``zone_name`` and record the outcome.

    On success the integration row becomes ``active`` (or
    ``pending_verification`` until the destination address is confirmed) and
    an alert is recorded. A DNS sync failure after a successful gateway is
    logged and does not fail the integration. Any provisioning failure sets
    the row to ``error`` with the message. Never raises.
    """
    try:
        provisioner = CloudflareProvisioner(api_token=api_token)
        result = await provisioner.provision(
            zone_name=zone_name,
            destination_email=destination_email,
            scan_url=scan_url,
        )
        ts = datetime.now(timezone.utc).isoformat()
        initial_status = "active" if result.destination_verified else "pending_verification"
        await execute_runtime_query(
            """
            UPDATE cloudflare_integration
            SET zone_id=?, account_id=?, worker_name=?, rule_id=?,
                destination_email=?, shared_secret_hash=?, status=?,
                error_message=NULL, updated_at=?
            WHERE id=?
            """,
            (
                result.zone_id,
                result.account_id,
                result.worker_name,
                result.rule_id,
                result.destination_email,
                result.shared_secret_hash,
                initial_status,
                ts,
                integration_id,
            ),
        )

        try:
            # DNS health is not gateway provisioning: keep the integration, surface DNS apart.
            await sync_domain_shield_dns(
                provisioner=provisioner,
                workspace_id=workspace_id,
                zone_name=zone_name,
                fix_spf=fix_spf,
                fix_dmarc=fix_dmarc,
                zone_id=result.zone_id,
                timestamp=ts,
            )
        except Exception as dns_exc:
            logger.warning(
                "Cloudflare gateway provisioned, but Domain Shield DNS sync failed for %s: %s",
                zone_name,
                dns_exc,
            )

        await execute_runtime_query(
            """
            INSERT INTO app_alert_history (
                id, workspace_id, domain, event_type, action_page,
                title, message, is_dismissed, created_at
            ) VALUES (?, ?, ?, 'cloudflare_sync', NULL, ?, ?, 0, ?)
            """,
            (
                str(uuid4()),
                workspace_id,
                zone_name.lower(),
                "Configuration Cloudflare appliquée",
                f"{zone_name} est synchronisé avec Cloudflare.",
                ts,
            ),
        )

        # No DNS work is needed on Sicurre's side to start receiving this
        # domain's DMARC reports: the wildcard consent record on
        # sicurre.com covers every client. See docs/ops/runbooks.md.
        logger.info("Cloudflare provisioning complete for zone %s", zone_name)
    except (CloudflareAPIError, Exception) as exc:
        logger.exception("Cloudflare provisioning failed: %s", exc)
        ts = datetime.now(timezone.utc).isoformat()
        await execute_runtime_query(
            "UPDATE cloudflare_integration SET status='error', error_message=?, updated_at=? WHERE id=?",
            (str(exc)[:500], ts, integration_id),
        )
