"""Apply the consented Domain Shield DNS fixes and refresh the status cache.

Used when a domain is connected and when the customer presses "Corriger
automatiquement". SPF and DMARC are the only records ever written; DKIM is
observed, never authored, because the signing key belongs to whoever sends
the mail.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from core.tls_certificate import get_ssl_expiry_days
from data_platform.services.cloudflare_provisioner import CloudflareProvisioner
from data_platform.services.dns_records import merge_dmarc, merge_spf, read_dns_state
from db.runtime import execute_runtime_query


async def measure_ssl(domain: str) -> tuple[int, int]:
    """Inspect the domain's public certificate for the shield status cache.

    Returns ``(ssl_valid, days_remaining)``, or ``(0, 0)`` when the
    certificate cannot be read, matching what the refresh path records.
    """
    days_remaining = await asyncio.to_thread(get_ssl_expiry_days, domain)
    return (1, days_remaining) if days_remaining >= 0 else (0, 0)


async def sync_domain_shield_dns(
    *,
    provisioner: CloudflareProvisioner,
    workspace_id: str,
    zone_name: str,
    fix_spf: bool,
    fix_dmarc: bool,
    zone_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Apply the selected fixes to the zone and upsert ``app_domain_shield_status``.

    ``zone_id`` skips the zone lookup when the caller has just provisioned it;
    ``timestamp`` lets the row share the provisioning time. Raises
    ``CloudflareAPIError`` when Cloudflare refuses a read or a write.
    """
    if zone_id is None:
        zone_id, _ = await provisioner.get_zone(zone_name)
    dns_records = await provisioner.get_dns_records(zone_id)
    existing_spf_content, existing_dkim_content, existing_dmarc_content = read_dns_state(
        dns_records, zone_name
    )

    spf_val = 1 if "v=spf1" in existing_spf_content else 0
    spf_rec = existing_spf_content or None
    if fix_spf:
        spf_rec = merge_spf(existing_spf_content)
        await provisioner.deploy_dns_record(
            zone_id=zone_id,
            rec_type="TXT",
            name=zone_name,
            content=spf_rec,
            match_prefix="v=spf1",
        )
        spf_val = 1

    # DKIM is never written: the signing key belongs to whoever sends the mail
    # (Cloudflare's own selector for Email Routing, the customer's provider for
    # their own sending).
    dkim_val = 1 if existing_dkim_content else 0
    dkim_rec = existing_dkim_content or None

    dmarc_val = 1 if "v=DMARC1" in existing_dmarc_content else 0
    dmarc_rec = existing_dmarc_content or None
    if fix_dmarc:
        dmarc_rec = merge_dmarc(existing_dmarc_content)
        await provisioner.deploy_dns_record(
            zone_id=zone_id,
            rec_type="TXT",
            name=f"_dmarc.{zone_name}",
            content=dmarc_rec,
            match_prefix="v=DMARC1",
        )
        dmarc_val = 1

    dmarc_policy = "none"
    if dmarc_rec and "p=reject" in dmarc_rec:
        dmarc_policy = "reject"
    elif dmarc_rec and "p=quarantine" in dmarc_rec:
        dmarc_policy = "quarantine"
    dmarc_reporting_enabled = "dmarc@sicurre.com" in (dmarc_rec or "")

    rep_score = 100
    if not spf_val:
        rep_score -= 20
    if not dkim_val:
        rep_score -= 20
    if not dmarc_val:
        rep_score -= 25
    elif not dmarc_reporting_enabled:
        rep_score -= 10

    grade = "A"
    if rep_score >= 90:
        grade = "A"
    elif rep_score >= 80:
        grade = "B"
    elif rep_score >= 70:
        grade = "C"
    elif rep_score >= 60:
        grade = "D"
    else:
        grade = "F"

    ssl_val, ssl_days = await measure_ssl(zone_name)

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    await execute_runtime_query(
        """
        INSERT INTO app_domain_shield_status (
            domain, workspace_id, spf_valid, spf_record, dkim_valid, dkim_record,
            dmarc_valid, dmarc_record, dmarc_policy, ssl_valid, ssl_days_remaining,
            reputation_score, score_grade, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, domain) DO UPDATE SET
            workspace_id=excluded.workspace_id, spf_valid=excluded.spf_valid,
            spf_record=excluded.spf_record, dkim_valid=excluded.dkim_valid,
            dkim_record=excluded.dkim_record, dmarc_valid=excluded.dmarc_valid,
            dmarc_record=excluded.dmarc_record, dmarc_policy=excluded.dmarc_policy,
            ssl_valid=excluded.ssl_valid, ssl_days_remaining=excluded.ssl_days_remaining,
            reputation_score=excluded.reputation_score, score_grade=excluded.score_grade,
            updated_at=excluded.updated_at
        """,
        (
            zone_name,
            workspace_id,
            spf_val,
            spf_rec,
            dkim_val,
            dkim_rec,
            dmarc_val,
            dmarc_rec,
            dmarc_policy,
            ssl_val,
            ssl_days,
            rep_score,
            grade,
            ts,
        ),
    )
    return {
        "zone_id": zone_id,
        "dmarc_record": dmarc_rec,
        "dmarc_reporting_enabled": dmarc_reporting_enabled,
        "reputation_score": rep_score,
        "score_grade": grade,
        "updated_at": ts,
    }
