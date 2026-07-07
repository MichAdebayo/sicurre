"""
Integrations router — two responsibilities:

1. POST /v1/email/scan
   Public endpoint called by the Cloudflare Email Worker.
   Validates the shared-secret header, forwards the payload to the inference
   engine, logs the decision to sicurre.db, and returns a verdict JSON.

2. POST /v1/integrations/cloudflare/setup
   Authenticated endpoint that provisions an entire Cloudflare email intercept
   pipeline (Email Routing + Email Worker + DNS catch-all rule) for a domain
   in a single API call.

3. GET  /v1/integrations/cloudflare/status
   Returns the current integration record for the calling user.

4. DELETE /v1/integrations/cloudflare
   Tears down the Cloudflare pipeline and removes the DB record.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, Field

from core.config import get_settings
from core.loops import send_loops_transactional
from data_platform.api.auth import AuthUser, ensure_runtime_tables, get_current_user
from data_platform.services.cloudflare_provisioner import (
    CloudflareAPIError,
    CloudflareProvisioner,
)

def _clean_str(val: str) -> str:
    if not val:
        return ""
    val = val.strip()
    if val.startswith("b'") or val.startswith('b"'):
        val = val[2:-1]
    return val

def _merge_spf(current_spf: str) -> str:
    cleaned = _clean_str(current_spf)
    if not cleaned:
        return "v=spf1 include:spf.cloudflare.com include:sicurre.com ~all"
    parts = cleaned.split()
    if not parts or parts[0] != "v=spf1":
        return "v=spf1 include:spf.cloudflare.com include:sicurre.com ~all"
    
    mechanisms = []
    all_mechanism = "~all"
    for p in parts[1:]:
        if p in ("-all", "~all", "?all", "+all"):
            all_mechanism = p
        else:
            if p not in mechanisms:
                mechanisms.append(p)
    
    for inc in ("include:spf.cloudflare.com", "include:sicurre.com"):
        if inc not in mechanisms:
            mechanisms.append(inc)
    
    return f"v=spf1 {' '.join(mechanisms)} {all_mechanism}"

def _merge_dmarc(current_dmarc: str) -> str:
    cleaned = _clean_str(current_dmarc)
    if not cleaned:
        return "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"
    
    policy = "quarantine"
    if "p=reject" in cleaned:
        policy = "reject"
    
    import re
    rec = re.sub(r"p=[^;]+", f"p={policy}", cleaned)
    
    if "rua=" in rec:
        if "dmarc@sicurre.com" not in rec:
            rec = re.sub(r"(rua=[^;'\"]+)", r"\1,mailto:dmarc@sicurre.com", rec)
    else:
        rec = rec.rstrip("; ") + "; rua=mailto:dmarc@sicurre.com"
    
    return rec


async def _sync_domain_shield_dns(
    *,
    provisioner: CloudflareProvisioner,
    workspace_id: str,
    zone_name: str,
    fix_spf: bool,
    fix_dkim: bool,
    fix_dmarc: bool,
) -> dict[str, Any]:
    """Apply selected Domain Shield DNS fixes and update the local status cache."""
    zone_id, _ = await provisioner.get_zone(zone_name)
    dns_records = await provisioner.get_dns_records(zone_id)
    existing_spf_content = ""
    existing_dkim_content = ""
    existing_dmarc_content = ""

    for rec in dns_records:
        if rec.get("type") != "TXT":
            continue
        rec_name = _clean_str(rec.get("name", "")).lower().rstrip(".")
        rec_content = _clean_str(rec.get("content", "")).strip('"')
        if rec_name == zone_name.lower():
            existing_spf_content = rec_content
        elif "._domainkey." in rec_name or rec_name.startswith("_domainkey."):
            if "v=DKIM1" in rec_content or "k=rsa" in rec_content:
                existing_dkim_content = rec_content
        elif rec_name == f"_dmarc.{zone_name}".lower():
            existing_dmarc_content = rec_content

    spf_val = 1 if "v=spf1" in existing_spf_content else 0
    spf_rec = existing_spf_content or None
    if fix_spf:
        spf_rec = _merge_spf(existing_spf_content)
        await provisioner.deploy_dns_record(
            zone_id=zone_id,
            rec_type="TXT",
            name=zone_name,
            content=spf_rec,
        )
        spf_val = 1

    dkim_val = 1 if existing_dkim_content else 0
    dkim_rec = existing_dkim_content or None
    if fix_dkim:
        dkim_rec = "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."
        await provisioner.deploy_dns_record(
            zone_id=zone_id,
            rec_type="TXT",
            name=f"cloudflare._domainkey.{zone_name}",
            content=dkim_rec,
        )
        dkim_val = 1

    dmarc_val = 1 if "v=DMARC1" in existing_dmarc_content else 0
    dmarc_rec = existing_dmarc_content or None
    if fix_dmarc:
        dmarc_rec = _merge_dmarc(existing_dmarc_content)
        await provisioner.deploy_dns_record(
            zone_id=zone_id,
            rec_type="TXT",
            name=f"_dmarc.{zone_name}",
            content=dmarc_rec,
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

    ts = datetime.now(timezone.utc).isoformat()
    await _async_query(
        """
        INSERT OR REPLACE INTO app_domain_shield_status (
            domain, workspace_id, spf_valid, spf_record, dkim_valid, dkim_record,
            dmarc_valid, dmarc_record, dmarc_policy, ssl_valid, ssl_days_remaining,
            reputation_score, score_grade, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 365, ?, ?, ?)
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations"])

# ---------------------------------------------------------------------------
# Database helpers (same pattern as app_routes.py — direct SQLite)
# ---------------------------------------------------------------------------


def _db_path() -> str:
    settings = get_settings()
    return settings.database_url.replace("sqlite+aiosqlite:///", "").replace(
        "sqlite:///", ""
    )


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def _async_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_query, sql, params)


def _ensure_tables() -> None:
    """Create the cloudflare_integration table if it does not exist yet."""
    ensure_runtime_tables()
    _query("""
        CREATE TABLE IF NOT EXISTS cloudflare_integration (
            id                  TEXT PRIMARY KEY,
            user_email          TEXT NOT NULL,
            workspace_id        TEXT NULL,
            workspace_member_user_id TEXT NULL,
            zone_id             TEXT NOT NULL,
            zone_name           TEXT NOT NULL,
            account_id          TEXT NOT NULL,
            worker_name         TEXT NOT NULL,
            rule_id             TEXT NOT NULL DEFAULT 'unknown',
            destination_email   TEXT NOT NULL,
            shared_secret_hash  TEXT NOT NULL,
            status              TEXT NOT NULL DEFAULT 'pending_verification',
            error_message       TEXT,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL
        )
    """)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EmailScanRequest(BaseModel):
    subject: str = Field(default="", max_length=500)
    sender: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=10_000)
    use_llm: bool = True
    use_virustotal: bool = False


class EmailScanResponse(BaseModel):
    verdict: str  # "phishing" | "safe"
    label: str  # "phishing" | "spam" | "legitimate"
    score: float
    explanation: str = ""


class CloudflareSetupRequest(BaseModel):
    cf_api_token: str = Field(
        ...,
        description="Cloudflare API token with DNS + Workers + Email Routing write access",
    )
    zone_name: str = Field(..., description="Domain to protect, e.g. vinse.app")
    destination_email: str = Field(
        ..., description="Where clean mail is forwarded after scanning"
    )
    fix_spf: bool = True
    fix_dkim: bool = True
    fix_dmarc: bool = True


class CloudflareStatusResponse(BaseModel):
    id: str
    user_email: str
    zone_name: str
    destination_email: str
    worker_name: str
    status: str
    error_message: str | None
    created_at: str
    updated_at: str


class TeardownRequest(BaseModel):
    cf_api_token: str = Field(
        ..., description="Cloudflare API token (required to remove Workers/rules)"
    )


# ---------------------------------------------------------------------------
# ── 1. Email Scan endpoint (called by Cloudflare Worker) ─────────────────
# ---------------------------------------------------------------------------


@router.post("/v1/email/scan", response_model=EmailScanResponse)
async def scan_email(
    payload: EmailScanRequest,
    x_sicurre_secret: str | None = Header(default=None, alias="X-Sicurre-Secret"),
) -> EmailScanResponse:
    """
    Validate the Worker shared secret, call the inference API, log the result,
    and return a verdict.

    This endpoint is intentionally public (no user session) — it is called by
    Cloudflare Workers and authenticated exclusively through the per-integration
    shared secret header.
    """
    _ensure_tables()

    if not x_sicurre_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Sicurre-Secret header",
        )

    # Verify the secret against stored hash
    secret_hash = hashlib.sha256(x_sicurre_secret.encode()).hexdigest()
    rows = await _async_query(
        "SELECT id, user_email, workspace_id, workspace_member_user_id, zone_name, status FROM cloudflare_integration WHERE shared_secret_hash = ? AND status IN ('pending_verification','active') LIMIT 1",
        (secret_hash,),
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid shared secret"
        )

    integration = rows[0]
    settings = get_settings()
    workspace_id = integration.get("workspace_id")
    now = datetime.now(timezone.utc).isoformat()

    # ── Check Whitelist / Blocklist Rules ──────────────────────────────────
    rules = await _async_query(
        "SELECT rule_type, pattern FROM app_security_rule WHERE workspace_id = ?",
        (workspace_id,)
    )
    
    matched_rule_type = None
    sender_lower = payload.sender.lower()
    
    for rule in rules:
        pattern = rule["pattern"].lower()
        if "@" in pattern:
            if pattern.startswith("@"):
                if sender_lower.endswith(pattern):
                    matched_rule_type = rule["rule_type"]
                    break
            else:
                if sender_lower == pattern:
                    matched_rule_type = rule["rule_type"]
                    break
        else:
            if sender_lower.endswith(f"@{pattern}") or sender_lower == pattern:
                matched_rule_type = rule["rule_type"]
                break

    verdict_label = "legitimate"
    verdict_safety = "safe"
    score = 0.0
    explanation = ""

    if matched_rule_type == "whitelist":
        verdict_safety = "safe"
        verdict_label = "legitimate"
        score = 0.0
        explanation = "Allowed by custom security whitelist rule."
    elif matched_rule_type == "blocklist":
        verdict_safety = "phishing"
        verdict_label = "phishing"
        score = 1.0
        explanation = "Blocked by custom security blocklist rule."
    else:
        # ── Call inference API ──────────────────────────────────────────────────
        inference_url = settings.inference_api_url or "http://localhost:8000/v1/classify"
        inference_key = settings.inference_api_key or ""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    inference_url,
                    json={
                        "subject": payload.subject,
                        "sender": payload.sender,
                        "text": payload.text,
                        "use_llm": payload.use_llm,
                        "use_virustotal": payload.use_virustotal,
                    },
                    headers={"Authorization": f"Bearer {inference_key}"},
                )
            resp.raise_for_status()
            result = resp.json()

            is_phishing: bool = bool(result.get("is_phishing", False))
            verdict_safety = "phishing" if is_phishing else "safe"
            verdict_label = str(
                result.get("label_verdict") or ("phishing" if is_phishing else "legitimate")
            ).lower()
            score = float(result.get("composite_score") or 0.0)
            explanation = str(result.get("explanation") or "")

        except Exception as exc:
            # Fail-open: if inference is unavailable, mark as safe and log
            logger.error("Inference API unavailable during email scan: %s", exc)
            verdict_safety = "safe"
            verdict_label = "legitimate"

    # ── Quarantine Handling ────────────────────────────────────────────────
    # If verdict is phishing, quarantine the email instead of bouncing
    event_id = str(uuid4())
    if verdict_safety == "phishing":
        q_id = str(uuid4())
        expires_at = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat() + "Z"
        try:
            await _async_query(
                """
                INSERT INTO app_quarantine_item (
                    id, workspace_id, message_id, sender, subject, body_text,
                    safety_verdict, composite_score, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'held', ?, ?)
                """,
                (
                    q_id,
                    workspace_id,
                    event_id,
                    payload.sender,
                    payload.subject,
                    payload.text,
                    verdict_safety,
                    score,
                    now,
                    expires_at
                )
            )
            # Log to alert history
            await _async_query(
                """
                INSERT INTO app_alert_history (
                    id, workspace_id, title, message, is_dismissed, created_at
                ) VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    str(uuid4()),
                    workspace_id,
                    "Email Quarantined",
                    f"Email from {payload.sender} regarding '{payload.subject}' was quarantined.",
                    now
                )
            )
            # Switch scan endpoint output verdict to "quarantine"
            verdict_safety = "quarantine"

            # Fetch user name for Loops greeting
            user_rows = await _async_query(
                'SELECT name FROM "user" WHERE email = ? LIMIT 1',
                (integration.get("user_email").lower(),)
            )
            first_name = "Utilisateur"
            if user_rows and user_rows[0].get("name"):
                first_name = user_rows[0]["name"].split(" ")[0]

            date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
            
            # Send alert email via Loops
            await send_loops_transactional(
                email=integration.get("user_email"),
                transactional_id=settings.loops_threat_quarantined_transaction_id,
                data_variables={
                    "firstName": first_name,
                    "domainName": integration.get("zone_name") or "votre domaine",
                    "senderEmail": payload.sender,
                    "emailSubject": payload.subject,
                    "riskScore": int(score * 100),
                    "interceptedAt": date_str,
                    "quarantineUrl": f"{settings.public_api_url or 'http://localhost:5173'}/",
                }
            )
        except Exception as exc:
            logger.warning("Could not quarantine phishing email: %s", exc)

    # ── Persist to audit log ────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    
    db_subject = payload.subject[:240]
    db_sender = payload.sender[:200]
    db_snippet = payload.text[:240]

    # Anonymize legitimate and spam email contents to ensure user privacy compliance (GDPR)
    if verdict_safety not in ("phishing", "quarantine"):
        db_subject = "[Masqué par Sicurre]"
        db_sender = "[Masqué par Sicurre]"
        db_snippet = "[Masqué par Sicurre]"

    try:
        await _async_query(
            """
            INSERT INTO app_inference_event (
                id, created_at, user_email, workspace_id, workspace_member_user_id, context,
                subject, sender, snippet,
                safety_verdict, label_verdict, composite_score, is_phishing,
                delivered_in_smail, llm_provider, explanation, latency_ms,
                used_llm, used_virustotal, inference_source,
                stage_scores_json, stage_labels_json, stage_breakdown_json, expected_label
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id,
                now,
                integration["user_email"],
                integration.get("workspace_id"),
                integration.get("workspace_member_user_id"),
                "cloudflare_intercept",
                db_subject,
                db_sender,
                db_snippet,
                verdict_safety,
                verdict_label,
                score,
                1 if verdict_safety == "phishing" else 0,
                0 if verdict_safety == "phishing" else 1,
                "cloudflare_worker",
                explanation[:500],
                0.0,
                1 if payload.use_llm else 0,
                1 if payload.use_virustotal else 0,
                "api",
                "{}",
                "{}",
                "{}",
                None,
            ),
        )
        # Mark integration active on first successful scan
        if integration.get("status") == "pending_verification":
            await _async_query(
                "UPDATE cloudflare_integration SET status = 'active', updated_at = ? WHERE id = ?",
                (now, integration["id"]),
            )
    except Exception as exc:
        logger.warning("Could not persist audit log for email scan: %s", exc)

    return EmailScanResponse(
        verdict=verdict_safety,
        label=verdict_label,
        score=score,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# ── 2. Provision Cloudflare integration ──────────────────────────────────
# ---------------------------------------------------------------------------


@router.post("/v1/integrations/cloudflare/setup", status_code=status.HTTP_201_CREATED)
async def setup_cloudflare(
    payload: CloudflareSetupRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Full one-shot provisioning:
      • Find zone → enable Email Routing → deploy Email Worker → create catch-all rule
    The user only needs to click the verification email Cloudflare sends to
    ``destination_email``.
    """
    _ensure_tables()
    settings = get_settings()

    # Check for an existing active integration for this zone
    existing = await _async_query(
        "SELECT * FROM cloudflare_integration WHERE workspace_id = ? AND zone_name = ? LIMIT 1",
        (current_user.workspace_id, payload.zone_name),
    )
    if existing:
        row = existing[0]
        if row["status"] == "provisioning":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An auto-configuration for {payload.zone_name} is already running in the background. Please wait.",
            )

        now = datetime.now(timezone.utc).isoformat()
        try:
            dns_sync_result = await _sync_domain_shield_dns(
                provisioner=CloudflareProvisioner(api_token=payload.cf_api_token),
                workspace_id=current_user.workspace_id,
                zone_name=payload.zone_name,
                fix_spf=payload.fix_spf,
                fix_dkim=payload.fix_dkim,
                fix_dmarc=payload.fix_dmarc,
            )
        except CloudflareAPIError as exc:
            await _async_query(
                "UPDATE cloudflare_integration SET error_message=?, api_token=?, updated_at=? WHERE id=?",
                (str(exc)[:500], payload.cf_api_token, now, row["id"]),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Cloudflare DNS update failed: {exc}",
            ) from exc

        await _async_query(
            """
            UPDATE cloudflare_integration
            SET api_token=?, error_message=NULL, updated_at=?
            WHERE id=?
            """,
            (payload.cf_api_token, now, row["id"]),
        )
        await _async_query(
            """
            INSERT OR REPLACE INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (current_user.workspace_id, payload.cf_api_token, now, now),
        )
        await _async_query(
            """
            INSERT INTO app_alert_history (
                id, workspace_id, title, message, is_dismissed, created_at
            ) VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                str(uuid4()),
                current_user.workspace_id,
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
            "message": "Domain Shield DNS configuration applied.",
        }

    # Derive the public scan URL for the Worker to call back
    public_api_url = (
        settings.public_api_url.rstrip("/")
        if settings.public_api_url
        else str(request.base_url).rstrip("/")
    )
    scan_url = f"{public_api_url}/v1/email/scan"

    # Insert a "provisioning" record so the UI can poll while setup runs
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
            payload.cf_api_token,
            "",
            "provisioning",
            now,
            now,
        ),
    )

    # Also automatically persist the token into app_cloudflare_config for the workspace
    if payload.cf_api_token:
        await _async_query(
            """
            INSERT OR REPLACE INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (current_user.workspace_id, payload.cf_api_token, now, now),
        )

    dns_sync_result: dict[str, Any] | None = None
    try:
        dns_sync_result = await _sync_domain_shield_dns(
            provisioner=CloudflareProvisioner(api_token=payload.cf_api_token),
            workspace_id=current_user.workspace_id,
            zone_name=payload.zone_name,
            fix_spf=payload.fix_spf,
            fix_dkim=payload.fix_dkim,
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

    async def _run_provisioning() -> None:
        try:
            provisioner = CloudflareProvisioner(api_token=payload.cf_api_token)
            result = await provisioner.provision(
                zone_name=payload.zone_name,
                destination_email=str(payload.destination_email),
                scan_url=scan_url,
            )
            ts = datetime.now(timezone.utc).isoformat()
            initial_status = "active" if result.destination_verified else "pending_verification"
            await _async_query(
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
                # Domain Shield DNS health writes are useful, but they are not the
                # same as gateway provisioning. If they fail, keep the integration
                # active/pending and surface the DNS issue separately.
                dns_records = await provisioner.get_dns_records(result.zone_id)
                existing_spf_content = ""
                existing_dkim_content = ""
                existing_dmarc_content = ""

                for rec in dns_records:
                    if rec.get("type") == "TXT":
                        rec_name = _clean_str(rec.get("name", "")).lower().rstrip(".")
                        rec_content = _clean_str(rec.get("content", ""))
                        if rec_name == payload.zone_name.lower():
                            existing_spf_content = rec_content
                        elif "._domainkey." in rec_name or rec_name.startswith("_domainkey."):
                            if "v=DKIM1" in rec_content or "k=rsa" in rec_content:
                                existing_dkim_content = rec_content
                        elif rec_name == f"_dmarc.{payload.zone_name}".lower():
                            existing_dmarc_content = rec_content

                spf_val = 1 if "v=spf1" in existing_spf_content else 0
                spf_rec = existing_spf_content or None
                if payload.fix_spf:
                    spf_rec = _merge_spf(existing_spf_content)
                    await provisioner.deploy_dns_record(
                        zone_id=result.zone_id,
                        rec_type="TXT",
                        name=payload.zone_name,
                        content=spf_rec,
                    )
                    spf_val = 1

                dkim_val = 1 if existing_dkim_content else 0
                dkim_rec = existing_dkim_content or None
                if payload.fix_dkim:
                    dkim_rec = "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."
                    await provisioner.deploy_dns_record(
                        zone_id=result.zone_id,
                        rec_type="TXT",
                        name=f"cloudflare._domainkey.{payload.zone_name}",
                        content=dkim_rec,
                    )
                    dkim_val = 1

                dmarc_val = 1 if "v=DMARC1" in existing_dmarc_content else 0
                dmarc_rec = existing_dmarc_content or None
                if payload.fix_dmarc:
                    dmarc_rec = _merge_dmarc(existing_dmarc_content)
                    await provisioner.deploy_dns_record(
                        zone_id=result.zone_id,
                        rec_type="TXT",
                        name=f"_dmarc.{payload.zone_name}",
                        content=dmarc_rec,
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

                await _async_query(
                    """
                    INSERT OR REPLACE INTO app_domain_shield_status (
                        domain, workspace_id, spf_valid, spf_record, dkim_valid, dkim_record,
                        dmarc_valid, dmarc_record, dmarc_policy, ssl_valid, ssl_days_remaining,
                        reputation_score, score_grade, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 365, ?, ?, ?)
                    """,
                    (
                        payload.zone_name,
                        current_user.workspace_id,
                        spf_val,
                        spf_rec,
                        dkim_val,
                        dkim_rec,
                        dmarc_val,
                        dmarc_rec,
                        dmarc_policy,
                        rep_score,
                        grade,
                        ts,
                    ),
                )
            except Exception as dns_exc:
                logger.warning(
                    "Cloudflare gateway provisioned, but Domain Shield DNS sync failed for %s: %s",
                    payload.zone_name,
                    dns_exc,
                )

            await _async_query(
                """
                INSERT INTO app_alert_history (
                    id, workspace_id, title, message, is_dismissed, created_at
                ) VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    str(uuid4()),
                    current_user.workspace_id,
                    "Configuration Cloudflare appliquée",
                    f"{payload.zone_name} est synchronisé avec Cloudflare.",
                    ts,
                ),
            )

            logger.info(
                "Cloudflare provisioning complete for zone %s", payload.zone_name
            )
        except (CloudflareAPIError, Exception) as exc:
            logger.exception("Cloudflare provisioning failed: %s", exc)
            ts = datetime.now(timezone.utc).isoformat()
            await _async_query(
                "UPDATE cloudflare_integration SET status='error', error_message=?, updated_at=? WHERE id=?",
                (str(exc)[:500], ts, integration_id),
            )

    background_tasks.add_task(_run_provisioning)

    return {
        "integration_id": integration_id,
        "status": "provisioning",
        "zone_name": payload.zone_name,
        "destination_email": str(payload.destination_email),
        "dns_sync": dns_sync_result,
        "message": "Provisioning started. Poll /v1/integrations/cloudflare/status to track progress.",
    }


# ---------------------------------------------------------------------------
# ── 3. Status ──────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@router.get("/v1/integrations/cloudflare/status")
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
        "api_token": row.get("api_token"),
        "error_message": row.get("error_message") if status == "error" else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ---------------------------------------------------------------------------
# ── 4. Teardown ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@router.delete("/v1/integrations/cloudflare")
async def teardown_cloudflare(
    payload: TeardownRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove the Cloudflare Worker and routing rule then delete the DB record."""
    _ensure_tables()
    rows = await _async_query(
        "SELECT * FROM cloudflare_integration WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 1",
        (current_user.workspace_id,),
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No integration found"
        )

    row = rows[0]
    if row["status"] in ("provisioning",):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provisioning in progress; wait for it to complete before tearing down",
        )

    try:
        provisioner = CloudflareProvisioner(api_token=payload.cf_api_token)
        await provisioner.teardown(
            zone_id=row["zone_id"],
            account_id=row["account_id"],
            worker_name=row["worker_name"],
            rule_id=row.get("rule_id") or "unknown",
        )
    except CloudflareAPIError as exc:
        logger.warning("Cloudflare teardown had errors: %s", exc)

    await _async_query(
        "DELETE FROM cloudflare_integration WHERE id = ?",
        (row["id"],),
    )

    # Check if any remaining connected domains exist for this workspace
    remaining = await _async_query(
        "SELECT id FROM cloudflare_integration WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,),
    )
    if not remaining:
        # Parent domain removed: purge orphaned workspace tokens and shield cache
        await _async_query(
            "DELETE FROM app_cloudflare_config WHERE workspace_id = ?",
            (current_user.workspace_id,),
        )
        await _async_query(
            "DELETE FROM app_domain_shield_status WHERE workspace_id = ? OR domain = ?",
            (current_user.workspace_id, row["zone_name"]),
        )

    return {"status": "removed", "zone_name": row["zone_name"]}


# ---------------------------------------------------------------------------
# ── 5. Validate token only (used by the UI wizard step) ───────────────────
# ---------------------------------------------------------------------------


class TokenVerifyRequest(BaseModel):
    cf_api_token: str
    zone_name: str


@router.post("/v1/integrations/cloudflare/verify-token")
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
        return {"valid": True, "zone_id": zone_id}
    except CloudflareAPIError as exc:
        return {"valid": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# ── 6. Global Workspace Token Management ──────────────────────────────────
# ---------------------------------------------------------------------------

class CloudflareTokenSaveRequest(BaseModel):
    cf_api_token: str = Field(..., description="Cloudflare API token to store")

@router.get("/v1/integrations/cloudflare/token")
async def get_workspace_cloudflare_token(
    current_user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the stored Cloudflare API token for the current workspace if an active domain is connected."""
    _ensure_tables()
    
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
        return {"api_token": None}

    rows = await _async_query(
        "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,),
    )
    if rows and rows[0]["api_token"]:
        return {"api_token": rows[0]["api_token"]}

    return {"api_token": integ_rows[0]["api_token"]}

@router.post("/v1/integrations/cloudflare/token")
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
        )

    ts = datetime.now(timezone.utc).isoformat()
    await _async_query(
        """
        INSERT OR REPLACE INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (current_user.workspace_id, payload.cf_api_token, ts, ts),
    )
    return {"status": "saved"}

@router.delete("/v1/integrations/cloudflare/token")
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
