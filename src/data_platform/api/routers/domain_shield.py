"""Domain Shield: the SPF, DKIM, DMARC, certificate and blocklist status of a domain."""

from __future__ import annotations

import asyncio
import ipaddress
import uuid
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from core.config import get_settings
from core.secret_cipher import decrypt_secret
from core.tls_certificate import get_ssl_expiry_days
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import DomainShieldResponse
from data_platform.api.workspace_scope import require_workspace_domain
from data_platform.services.notification_policy import notification_is_allowed
from db.runtime import execute_runtime_query

router = APIRouter(tags=["app-ui-flows"])


def _classify_blocklist_response(provider: str, addresses: list[str]) -> tuple[bool, str | None]:
    """Distinguish a real listing from a DNSBL access/error response."""
    parsed = []
    for address in addresses:
        with suppress(ValueError):
            parsed.append(ipaddress.ip_address(address))

    if provider == "Spamhaus DBL":
        if any(str(address).startswith("127.255.255.") for address in parsed):
            # 127.255.255.252/.254 are DQS misconfiguration codes, not a real listing.
            return False, "Spamhaus indisponible depuis le résolveur du serveur"
        return any(address in ipaddress.ip_network("127.0.0.0/16") for address in parsed), None

    if provider == "SURBL List":
        if any(str(address) == "127.0.0.1" for address in parsed):
            return False, "SURBL indisponible depuis le résolveur du serveur"
        return any(address in ipaddress.ip_network("127.0.0.0/8") for address in parsed), None

    return False, None


async def _check_domain_blacklists(
    domain: str,
    *,
    dqs_key: str | None = None,
) -> tuple[list[str], list[str]]:
    """Query Spamhaus DBL and SURBL for domain reputation listings."""
    import dns.resolver

    if dqs_key:
        spamhaus_zone = f"{dqs_key}.dbl.dq.spamhaus.net"
    else:
        spamhaus_zone = "dbl.spamhaus.org"

    blacklists = {spamhaus_zone: "Spamhaus DBL", "multi.surbl.org": "SURBL List"}
    listed_on: list[str] = []
    unavailable: list[str] = []
    for rbl, name in blacklists.items():
        try:
            query_host = f"{domain}.{rbl}"
            answers = await asyncio.to_thread(dns.resolver.resolve, query_host, "A")
            listed, error = _classify_blocklist_response(name, [str(answer) for answer in answers])
            if listed:
                listed_on.append(name)
            elif error and not (dqs_key and name == "SURBL List"):
                unavailable.append(error)
        except Exception:
            pass
    return listed_on, unavailable


@router.get(
    "/v1/domain-shield/{domain}/status",
    response_model=DomainShieldResponse,
    response_model_exclude_unset=True,
)
async def check_domain_shield_status(
    domain: str, refresh: bool = False, current_user: AuthUser = Depends(get_current_user)
):
    await require_workspace_domain(domain, current_user.workspace_id)
    # Run dynamic blacklist check
    settings = get_settings()
    blacklists_listed, blacklist_errors = await _check_domain_blacklists(
        domain,
        dqs_key=settings.spamhaus_dqs_key,
    )
    blacklist_error = "; ".join(blacklist_errors) or None

    # Try fetching from DB cache first
    if not refresh:
        cached_rows = await execute_runtime_query(
            "SELECT * FROM app_domain_shield_status WHERE domain = ? AND workspace_id = ? LIMIT 1",
            (domain, current_user.workspace_id),
        )
        if cached_rows:
            row = cached_rows[0]
            score = int(row["reputation_score"])
            cached_ssl_days = int(row["ssl_days_remaining"])
            with suppress(TypeError, ValueError):
                updated_at = datetime.fromisoformat(str(row["updated_at"]).rstrip("Z"))
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                elapsed_days = max(0, (datetime.now(timezone.utc) - updated_at).days)
                cached_ssl_days = max(0, cached_ssl_days - elapsed_days)
            # The cached read must name why a certificate is not valid, as the
            # refresh path does.
            ssl_measured = bool(row["ssl_valid"])
            ssl_is_valid = ssl_measured and cached_ssl_days > 0
            if ssl_is_valid:
                ssl_error = None
            elif ssl_measured:
                ssl_error = "The measured certificate has expired"
            else:
                ssl_error = "Unable to inspect the public certificate"

            if blacklists_listed:
                score = max(30, score - 30 * len(blacklists_listed))

            # Recalculate score grade if score drops due to blacklists
            if score >= 90:
                grade = "A"
            elif score >= 80:
                grade = "B"
            elif score >= 70:
                grade = "C"
            elif score >= 60:
                grade = "D"
            else:
                grade = "F"

            return {
                "spf": {
                    "valid": bool(row["spf_valid"]),
                    "record": row["spf_record"],
                    "error": None if row["spf_valid"] else "Not configured",
                },
                "dkim": {
                    "valid": bool(row["dkim_valid"]),
                    "record": row["dkim_record"],
                    "error": None if row["dkim_valid"] else "Not configured",
                },
                "dmarc": {
                    "valid": bool(row["dmarc_valid"]),
                    "record": row["dmarc_record"],
                    "policy": row["dmarc_policy"] or "none",
                    "reporting_enabled": "dmarc@sicurre.com" in (row["dmarc_record"] or ""),
                    "error": None if row["dmarc_valid"] else "Not configured",
                },
                "ssl": {
                    "valid": ssl_is_valid,
                    "days_remaining": cached_ssl_days,
                    "auto_renew": ssl_is_valid,
                    "error": ssl_error,
                },
                "reputation_score": score,
                "score_grade": grade,
                "blacklists": {
                    "listed": len(blacklists_listed) > 0,
                    "matched": blacklists_listed,
                    "error": blacklist_error,
                },
                "updated_at": row["updated_at"],
            }

    import dns.resolver

    status = {
        "spf": {"valid": False, "record": None, "error": "Not configured"},
        "dkim": {"valid": False, "record": None, "error": "Not configured"},
        "dmarc": {
            "valid": False,
            "record": None,
            "policy": "none",
            "reporting_enabled": False,
            "error": "Not configured",
        },
        "ssl": {
            "valid": False,
            "days_remaining": 0,
            "auto_renew": False,
            "error": "Not configured",
        },
        "reputation_score": 100,
        "score_grade": "A",
        "blacklists": {
            "listed": len(blacklists_listed) > 0,
            "matched": blacklists_listed,
            "error": blacklist_error,
        },
    }

    # 1. Query SPF
    try:
        answers = await asyncio.to_thread(dns.resolver.resolve, domain, "TXT")
        for rdata in answers:
            txt = "".join(
                s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s)
                for s in rdata.strings
            )
            if "v=spf1" in txt:
                status["spf"]["valid"] = True
                status["spf"]["record"] = txt
                status["spf"]["error"] = None
                break
    except Exception as e:
        status["spf"]["error"] = str(e)
        status["reputation_score"] -= 20

    # 2. Query DKIM
    discovered_selectors = []
    try:
        token_rows = await execute_runtime_query(
            "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
            (current_user.workspace_id,),
        )
        if token_rows and token_rows[0]["api_token"]:
            from data_platform.services.cloudflare_provisioner import CloudflareProvisioner

            settings = get_settings()
            api_token = decrypt_secret(
                token_rows[0]["api_token"],
                configured_key=settings.secret_encryption_key,
                environment=settings.environment,
            )
            provisioner = CloudflareProvisioner(api_token=api_token)
            try:
                zone_id, _ = await provisioner.get_zone(domain)
                records = await provisioner.get_dns_records(zone_id)
                for rec in records:
                    name = str(rec.get("name", ""))
                    if "_domainkey" in name and rec.get("type") == "TXT":
                        parts = name.split("._domainkey")
                        if len(parts) > 0 and parts[0]:
                            selector = parts[0].strip()
                            if selector and selector not in discovered_selectors:
                                discovered_selectors.append(selector)
            except Exception:
                pass
    except Exception:
        pass

    dkim_selectors = [
        "cloudflare",
        "default",
        "google",
        "cf2024-1",
        "smtp",
        "mail",
        "k1",
        "mandrill",
        "s1",
        "s2",
    ]
    for sel in discovered_selectors:
        if sel not in dkim_selectors:
            dkim_selectors.append(sel)

    for selector in dkim_selectors:
        try:
            dkim_domain = f"{selector}._domainkey.{domain}"
            answers = await asyncio.to_thread(dns.resolver.resolve, dkim_domain, "TXT")
            for rdata in answers:
                txt = "".join(
                    s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s)
                    for s in rdata.strings
                )
                if "v=DKIM1" in txt or "k=rsa" in txt:
                    status["dkim"]["valid"] = True
                    status["dkim"]["record"] = txt
                    status["dkim"]["error"] = None
                    break
            if status["dkim"]["valid"]:
                break
        except Exception:
            pass

    if not status["dkim"]["valid"]:
        status["dkim"]["error"] = (
            f"DKIM record not found for selectors: {', '.join(dkim_selectors)}"
        )
        status["reputation_score"] -= 20

    # 3. Query DMARC
    try:
        dmarc_domain = f"_dmarc.{domain}"
        answers = await asyncio.to_thread(dns.resolver.resolve, dmarc_domain, "TXT")
        for rdata in answers:
            txt = "".join(
                s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s)
                for s in rdata.strings
            )
            if "v=DMARC1" in txt:
                status["dmarc"]["valid"] = True
                status["dmarc"]["record"] = txt
                status["dmarc"]["error"] = None

                if "p=reject" in txt:
                    status["dmarc"]["policy"] = "reject"
                elif "p=quarantine" in txt:
                    status["dmarc"]["policy"] = "quarantine"
                else:
                    status["dmarc"]["policy"] = "none"
                    status["reputation_score"] -= 10
                status["dmarc"]["reporting_enabled"] = "dmarc@sicurre.com" in txt
                if not status["dmarc"]["reporting_enabled"]:
                    status["reputation_score"] -= 10
                break
    except Exception as e:
        status["dmarc"]["error"] = str(e)
        status["reputation_score"] -= 25

    # 4. Check SSL Certificate
    expiry_days = await asyncio.to_thread(get_ssl_expiry_days, domain)
    if expiry_days >= 0:
        status["ssl"]["valid"] = True
        status["ssl"]["days_remaining"] = expiry_days
        status["ssl"]["auto_renew"] = True
        status["ssl"]["error"] = None
    else:
        status["ssl"]["valid"] = False
        status["ssl"]["days_remaining"] = 0
        status["ssl"]["auto_renew"] = False
        status["ssl"]["error"] = "Unable to inspect the public certificate"

    if blacklists_listed:
        status["reputation_score"] -= 30 * len(blacklists_listed)
    status["reputation_score"] = max(30, status["reputation_score"])
    score = status["reputation_score"]
    if score >= 90:
        status["score_grade"] = "A"
    elif score >= 80:
        status["score_grade"] = "B"
    elif score >= 70:
        status["score_grade"] = "C"
    elif score >= 60:
        status["score_grade"] = "D"
    else:
        status["score_grade"] = "F"

    # Save to status & handle SCD Type 2 history
    now_str = datetime.now(timezone.utc).isoformat() + "Z"

    # Check current active record in history
    hist_rows = await execute_runtime_query(
        "SELECT * FROM app_domain_shield_history WHERE workspace_id = ? "
        "AND lower(domain) = lower(?) AND is_current = 1 LIMIT 1",
        (current_user.workspace_id, domain),
    )

    has_changed = True
    if hist_rows:
        h = hist_rows[0]
        # Check if identical
        if (
            h["reputation_score"] == status["reputation_score"]
            and h["score_grade"] == status["score_grade"]
            and h["spf_valid"] == int(status["spf"]["valid"])
            and h["dkim_valid"] == int(status["dkim"]["valid"])
            and h["dmarc_valid"] == int(status["dmarc"]["valid"])
            and h["ssl_valid"] == int(status["ssl"]["valid"])
        ):
            has_changed = False

        # Trigger Loops DNS alert if score decreased compared to previous history record
        if status["reputation_score"] < h["reputation_score"]:
            settings = get_settings()
            anomalies = []
            if not status["spf"]["valid"]:
                anomalies.append("- SPF manquant ou invalide")
            if not status["dkim"]["valid"]:
                anomalies.append("- Signature DKIM absente ou non alignée")
            if not status["dmarc"]["valid"]:
                anomalies.append("- Politique DMARC absente (vulnérabilité critique d'usurpation)")

            anomaly_details = (
                "\n".join(anomalies) if anomalies else "- Détérioration globale des métriques DNS"
            )
            first_name = (
                current_user.display_name.split(" ")[0]
                if current_user.display_name
                else "Utilisateur"
            )

            await execute_runtime_query(
                "INSERT INTO app_alert_history "
                "(id, workspace_id, domain, event_type, action_page, title, message, "
                "is_dismissed, created_at) "
                "VALUES (?, ?, ?, 'domain_shield', 'domain-shield', ?, ?, 0, ?)",
                (
                    str(uuid.uuid4()),
                    current_user.workspace_id,
                    domain.lower(),
                    "Protection du domaine dégradée",
                    f"Le score de {domain} est passé de {h['reputation_score']} à "
                    f"{status['reputation_score']}.",
                    now_str,
                ),
            )
            preference_rows = await execute_runtime_query(
                "SELECT * FROM app_alert_preference WHERE workspace_id = ? "
                "AND lower(domain) = lower(?) LIMIT 1",
                (current_user.workspace_id, domain),
            )
            if notification_is_allowed(
                preference_rows[0] if preference_rows else None,
                datetime.now(timezone.utc),
                "domain_shield",
            ):
                from core.loops import send_loops_transactional

                await send_loops_transactional(
                    email=current_user.email,
                    transactional_id=settings.loops_dns_shield_alert_transaction_id,
                    data_variables={
                        "firstName": first_name,
                        "domainName": domain,
                        "dnsAnomalyDetails": anomaly_details,
                        "domainShieldUrl": f"{settings.public_api_url or 'http://localhost:5173'}/",
                    },
                )

    if has_changed:
        # Close previous active record
        await execute_runtime_query(
            "UPDATE app_domain_shield_history SET is_current = 0, end_date = ? "
            "WHERE workspace_id = ? AND lower(domain) = lower(?) AND is_current = 1",
            (now_str, current_user.workspace_id, domain),
        )
        # Create new history entry
        new_hist_id = str(uuid.uuid4())
        await execute_runtime_query(
            """
            INSERT INTO app_domain_shield_history (
                id, workspace_id, domain, reputation_score, score_grade,
                spf_valid, dkim_valid, dmarc_valid, ssl_valid, start_date, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                new_hist_id,
                current_user.workspace_id,
                domain,
                status["reputation_score"],
                status["score_grade"],
                int(status["spf"]["valid"]),
                int(status["dkim"]["valid"]),
                int(status["dmarc"]["valid"]),
                int(status["ssl"]["valid"]),
                now_str,
            ),
        )

    # Insert or replace latest status cache
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
            domain,
            current_user.workspace_id,
            int(status["spf"]["valid"]),
            status["spf"]["record"],
            int(status["dkim"]["valid"]),
            status["dkim"]["record"],
            int(status["dmarc"]["valid"]),
            status["dmarc"]["record"],
            status["dmarc"]["policy"],
            int(status["ssl"]["valid"]),
            status["ssl"]["days_remaining"],
            status["reputation_score"],
            status["score_grade"],
            now_str,
        ),
    )
    status["updated_at"] = now_str
    return status
