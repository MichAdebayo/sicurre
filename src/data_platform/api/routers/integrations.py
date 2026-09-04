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
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

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
from core.inference_client import get_inference_client
from core.loops import send_loops_transactional
from core.mime_headers import decode_mime_header, extract_mime_body
from core.rate_limit import limiter
from core.scan_metrics import observe_scan, observe_scan_failure, observe_stage
from core.secret_cipher import decrypt_secret, encrypt_secret
from data_platform.api.auth import AuthUser, ensure_runtime_tables, get_current_user
from data_platform.api.schemas.app_responses import (
    CloudflareIntegrationResponse,
    StatusResponse,
)
from data_platform.api.schemas.integration_responses import (
    CloudflareSetupResponse,
    CloudflareTeardownResponse,
    CloudflareTokenStatusResponse,
    CloudflareTokenVerificationResponse,
    QuarantineCustodyResponse,
)
from data_platform.cleaning.normalization import anonymize_pii
from data_platform.services.cloudflare_provisioner import (
    CloudflareAPIError,
    CloudflareProvisioner,
)
from data_platform.services.email_context import derive_email_context
from data_platform.services.notification_policy import notification_is_allowed
from data_platform.services.quarantine_storage import build_quarantine_store
from db.runtime import execute_runtime_query


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
        INSERT INTO app_domain_shield_status (
            domain, workspace_id, spf_valid, spf_record, dkim_valid, dkim_record,
            dmarc_valid, dmarc_record, dmarc_policy, ssl_valid, ssl_days_remaining,
            reputation_score, score_grade, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 365, ?, ?, ?)
        ON CONFLICT(domain) DO UPDATE SET
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

# --------------------------------------------------------------------------- Database helpers


def _db_path() -> str:
    settings = get_settings()
    return settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


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
    return await execute_runtime_query(sql, params)


async def _timed_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Same as _async_query, but attributed to the "database" scan stage."""
    # Delegates through _async_query rather than calling the engine directly so
    # the existing module-level test seam keeps working.
    with observe_stage("database"):
        return await _async_query(sql, params)


def _ensure_tables() -> None:
    """Create application tables for local development only."""
    ensure_runtime_tables()


def _encrypt_provider_token(token: str) -> str:
    settings = get_settings()
    return encrypt_secret(
        token,
        configured_key=settings.secret_encryption_key,
        environment=settings.environment,
    )


# --------------------------------------------------------------------------- Pydantic schemas


class EmailScanRequest(BaseModel):
    message_id: str | None = Field(default=None, max_length=500)
    subject: str = Field(default="", max_length=500)
    sender: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=10_000)
    use_llm: bool = True
    use_virustotal: bool = False


class EmailScanResponse(BaseModel):
    event_id: str
    verdict: Literal["safe", "phishing", "quarantine"]
    label: Literal["phishing", "spam", "legitimate"]
    score: float = Field(ge=0, le=1)
    explanation: str = ""
    quarantine_id: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)


class CloudflareSetupRequest(BaseModel):
    cf_api_token: str | None = Field(
        default=None,
        description="Cloudflare API token with DNS + Workers + Email Routing write access",
    )
    zone_name: str = Field(..., description="Domain to protect, e.g. vinse.app")
    destination_email: str = Field(..., description="Where clean mail is forwarded after scanning")
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
    integration_id: str | None = Field(
        default=None, description="Specific connected-domain integration to remove"
    )
    cf_api_token: str | None = Field(
        default=None, description="Optional override for the stored Cloudflare API token"
    )


# --------------------------------------------------------------------------- ── 1.


@router.post("/v1/email/scan", response_model=EmailScanResponse)
@limiter.limit("600/minute")
async def scan_email(
    request: Request,
    payload: EmailScanRequest,
    x_sicurre_secret: str | None = Header(default=None, alias="X-Sicurre-Secret"),
) -> EmailScanResponse:
    """Validate the Worker shared secret, call the inference API, log the result, and return a verdict"""
    request_started_at = perf_counter()
    _ = request
    _ensure_tables()

    if not x_sicurre_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Sicurre-Secret header",
        )

    # Verify the secret against stored hash
    secret_hash = hashlib.sha256(x_sicurre_secret.encode()).hexdigest()
    rows = await _timed_query(
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
    message_id = payload.message_id.strip() if payload.message_id else ""
    event_id = (
        str(
            uuid5(
                NAMESPACE_URL,
                f"{workspace_id}:{integration.get('zone_name', '').lower()}:{message_id}",
            )
        )
        if message_id
        else str(uuid4())
    )
    legacy_event_id = (
        str(uuid5(NAMESPACE_URL, f"{workspace_id}:{message_id}")) if message_id else event_id
    )
    # Run concurrently: independent SELECTs costing 458 ms of the 2 s budget when serial.
    zone_name = integration.get("zone_name") or ""
    with observe_stage("database"):
        existing_quarantine, existing_event, rules = await asyncio.gather(
            _async_query(
                "SELECT id, message_id, safety_verdict, composite_score FROM app_quarantine_item "
                "WHERE workspace_id = ? AND lower(domain) = lower(?) "
                "AND message_id IN (?, ?) LIMIT 1",
                (workspace_id, zone_name, event_id, legacy_event_id),
            ),
            _async_query(
                "SELECT id, safety_verdict, label_verdict, composite_score, explanation, latency_ms "
                "FROM app_inference_event WHERE id IN (?, ?) AND workspace_id = ? "
                "AND lower(domain) = lower(?) LIMIT 1",
                (event_id, legacy_event_id, workspace_id, zone_name),
            ),
            _async_query(
                "SELECT rule_type, pattern FROM app_security_rule WHERE workspace_id = ? "
                "AND lower(domain) = lower(?)",
                (workspace_id, zone_name),
            ),
        )

    if existing_quarantine:
        held = existing_quarantine[0]
        return EmailScanResponse(
            event_id=str(held["message_id"]),
            verdict="quarantine",
            label=str(held["safety_verdict"]),
            score=float(held["composite_score"]),
            explanation="Existing idempotent quarantine decision.",
            quarantine_id=str(held["id"]),
        )
    if existing_event:
        event = existing_event[0]
        return EmailScanResponse(
            event_id=str(event["id"]),
            verdict=str(event["safety_verdict"]),
            label=str(event["label_verdict"]),
            score=float(event["composite_score"]),
            explanation=str(event.get("explanation") or "Existing idempotent decision."),
            latency_ms=float(event.get("latency_ms") or 0.0) or None,
        )

    # Decode RFC 2047 headers first so rules, classifier, audit and alert see readable text.
    payload.subject = decode_mime_header(payload.subject)
    payload.sender = decode_mime_header(payload.sender)
    # The Worker forwards the raw message, so strip the MIME envelope down to the body.
    payload.text = extract_mime_body(payload.text)

    # ── Check Whitelist / Blocklist Rules ──────────────────────────────────
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
    llm_provider = ""
    stage_scores: dict[str, Any] = {}
    stage_labels: dict[str, Any] = {}
    stage_breakdown: dict[str, Any] = {}
    # Stays None when a blocklist rule short-circuits before any model is consulted.
    model_version: str | None = None
    model_revision: str | None = None

    if matched_rule_type == "blocklist":
        verdict_safety = "phishing"
        verdict_label = "phishing"
        score = 1.0
        explanation = "Blocked by custom security blocklist rule."
        stage_scores = {"custom_rule": 1.0}
        stage_labels = {"custom_rule": "phishing"}
        stage_breakdown = {"custom_rule": {"active": True, "rule_type": "blocklist"}}
    else:
        # ── Call inference API ──────────────────────────────────────────────────
        inference_url = settings.inference_api_url or "http://localhost:8000/v1/classify"
        inference_key = settings.inference_api_key or ""
        with observe_stage("context"):
            mail_context = derive_email_context(
                subject=payload.subject,
                sender=payload.sender,
                text=payload.text,
                recipient_expected=matched_rule_type == "whitelist",
            )

        try:
            with observe_stage("inference"):
                # Shared, long-lived client: opening one per request paid a TLS
                # handshake to the inference host on every email.
                client = get_inference_client()
                resp = await client.post(
                    inference_url,
                    json={
                        "subject": payload.subject,
                        "sender": payload.sender,
                        "text": payload.text,
                        "use_llm": payload.use_llm,
                        "use_virustotal": payload.use_virustotal,
                        "mail_context": mail_context.as_payload(),
                    },
                    headers={"Authorization": f"Bearer {inference_key}"},
                )
            resp.raise_for_status()
            result = resp.json()

            # The inference service reports which model answered on every response.
            model_version = (resp.headers.get("X-Sicurre-Model-Version") or "").strip() or None
            model_revision = (resp.headers.get("X-Sicurre-Model-Revision") or "").strip() or None

            is_phishing: bool = bool(result.get("is_phishing", False))
            verdict_safety = "phishing" if is_phishing else "safe"
            verdict_label = str(
                result.get("label_verdict") or ("phishing" if is_phishing else "legitimate")
            ).lower()
            score = float(result.get("composite_score") or 0.0)
            explanation = str(result.get("explanation") or "")
            llm_provider = str(result.get("llm_provider") or "")
            stage_scores = dict(result.get("stage_scores") or {})
            stage_labels = dict(result.get("stage_labels") or {})
            stage_breakdown = dict(result.get("stage_breakdown") or {})
            if matched_rule_type == "whitelist":
                stage_breakdown["custom_rule"] = {
                    "active": True,
                    "rule_type": "whitelist",
                    "effect": "recipient_expected",
                }

        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.error("Inference API unavailable during email scan: %s", exc)
            observe_scan_failure(
                "inference_unavailable"
                if isinstance(exc, httpx.HTTPError)
                else "inference_contract"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Inference service is temporarily unavailable",
            ) from exc

    decision_latency_ms = round((perf_counter() - request_started_at) * 1000, 2)
    observe_scan(
        verdict=verdict_label,
        duration_seconds=decision_latency_ms / 1000.0,
        sla_seconds=settings.sla_latency_ms / 1000.0,
    )

    # ── Quarantine Handling ────────────────────────────────────────────────
    # If verdict is phishing, quarantine the email instead of bouncing
    quarantine_id: str | None = None
    classified_as_phishing = verdict_safety == "phishing"
    if verdict_safety == "phishing":
        quarantine_id = str(uuid4())
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=settings.quarantine_retention_days)
        ).isoformat()
        try:
            await _async_query(
                """
                INSERT INTO app_quarantine_item (
                    id, workspace_id, domain, message_id, sender, subject, body_text,
                    safety_verdict, composite_score, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'held', ?, ?)
                """,
                (
                    quarantine_id,
                    workspace_id,
                    str(integration.get("zone_name") or "").lower(),
                    event_id,
                    payload.sender,
                    payload.subject,
                    anonymize_pii(payload.text)[:4000],
                    verdict_safety,
                    score,
                    now,
                    expires_at,
                ),
            )
            # Log to alert history
            await _async_query(
                """
                INSERT INTO app_alert_history (
                    id, workspace_id, domain, event_type, action_page,
                    title, message, is_dismissed, created_at
                ) VALUES (?, ?, ?, 'phishing_quarantine', 'quarantine', ?, ?, 0, ?)
                """,
                (
                    str(uuid4()),
                    workspace_id,
                    str(integration.get("zone_name") or "").lower(),
                    "Email mis en quarantaine",
                    "Un email suspect a été intercepté. Consultez la quarantaine pour décider de son sort.",
                    now,
                ),
            )
            # Switch scan endpoint output verdict to "quarantine"
            verdict_safety = "quarantine"

            preference_rows = await _async_query(
                "SELECT * FROM app_alert_preference "
                "WHERE workspace_id = ? AND lower(domain) = lower(?) LIMIT 1",
                (workspace_id, integration.get("zone_name") or ""),
            )
            notification_time = datetime.now(timezone.utc)
            if notification_is_allowed(
                preference_rows[0] if preference_rows else None,
                notification_time,
                "phishing",
            ):
                user_rows = await _async_query(
                    'SELECT name FROM "user" WHERE email = ? LIMIT 1',
                    (integration.get("user_email").lower(),),
                )
                first_name = "Utilisateur"
                if user_rows and user_rows[0].get("name"):
                    first_name = user_rows[0]["name"].split(" ")[0]
                await send_loops_transactional(
                    email=integration.get("user_email"),
                    transactional_id=settings.loops_threat_quarantined_transaction_id,
                    data_variables={
                        "firstName": first_name,
                        "domainName": integration.get("zone_name") or "votre domaine",
                        # Loops declares this variable as `sender`; `senderEmail` returned 400.
                        "sender": payload.sender,
                        "emailSubject": payload.subject,
                        "riskScore": int(score * 100),
                        "interceptedAt": notification_time.strftime("%d/%m/%Y %H:%M UTC"),
                        "quarantineUrl": f"{settings.public_api_url or 'http://localhost:5173'}/",
                    },
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
                id, created_at, user_email, workspace_id, workspace_member_user_id, domain, context,
                subject, sender, snippet,
                safety_verdict, label_verdict, composite_score, is_phishing,
                delivered_in_smail, llm_provider, explanation, latency_ms,
                used_llm, used_virustotal, inference_source,
                stage_scores_json, stage_labels_json, stage_breakdown_json, expected_label,
                model_version, model_revision
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id,
                now,
                integration["user_email"],
                integration.get("workspace_id"),
                integration.get("workspace_member_user_id"),
                str(integration.get("zone_name") or "").lower(),
                "cloudflare_intercept",
                db_subject,
                db_sender,
                db_snippet,
                verdict_safety,
                verdict_label,
                score,
                1 if classified_as_phishing else 0,
                0 if classified_as_phishing else 1,
                llm_provider,
                explanation[:500],
                decision_latency_ms,
                1 if payload.use_llm else 0,
                1 if payload.use_virustotal else 0,
                "api",
                json.dumps(stage_scores, sort_keys=True, separators=(",", ":")),
                json.dumps(stage_labels, sort_keys=True, separators=(",", ":")),
                json.dumps(stage_breakdown, sort_keys=True, separators=(",", ":")),
                None,
                model_version,
                model_revision,
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
        event_id=event_id,
        verdict=verdict_safety,
        label=verdict_label,
        score=score,
        explanation=explanation,
        quarantine_id=quarantine_id,
        latency_ms=decision_latency_ms,
    )


@router.put(
    "/v1/email/quarantine/{item_id}/content",
    response_model=QuarantineCustodyResponse,
)
@limiter.limit("120/minute")
async def upload_quarantine_content(
    item_id: str,
    request: Request,
    x_sicurre_secret: str | None = Header(default=None, alias="X-Sicurre-Secret"),
) -> dict[str, Any]:
    """Persist original MIME after a Worker receives a quarantine verdict."""
    if not x_sicurre_secret:
        raise HTTPException(status_code=401, detail="Missing X-Sicurre-Secret header")
    secret_hash = hashlib.sha256(x_sicurre_secret.encode()).hexdigest()
    integrations = await _async_query(
        "SELECT workspace_id, zone_name FROM cloudflare_integration "
        "WHERE shared_secret_hash = ? AND status IN ('pending_verification','active') LIMIT 1",
        (secret_hash,),
    )
    if not integrations:
        raise HTTPException(status_code=401, detail="Invalid shared secret")
    workspace_id = integrations[0]["workspace_id"]
    domain = str(integrations[0]["zone_name"]).lower()
    items = await _async_query(
        "SELECT raw_storage_uri, raw_content_hash FROM app_quarantine_item "
        "WHERE id = ? AND workspace_id = ? AND lower(domain) = lower(?) "
        "AND status = 'held' LIMIT 1",
        (item_id, workspace_id, domain),
    )
    if not items:
        raise HTTPException(status_code=404, detail="Quarantined item not found")

    settings = get_settings()
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Raw MIME content is required")
    if len(payload) > settings.quarantine_max_message_bytes:
        raise HTTPException(status_code=413, detail="Message exceeds quarantine storage limit")
    content_hash = hashlib.sha256(payload).hexdigest()
    existing = items[0]
    if existing.get("raw_storage_uri"):
        if existing.get("raw_content_hash") != content_hash:
            raise HTTPException(status_code=409, detail="Quarantine content already exists")
        return {"status": "stored", "idempotent": True}

    stored = await build_quarantine_store(settings).write(
        workspace_id=str(workspace_id),
        item_id=item_id,
        payload=payload,
    )
    await _async_query(
        "UPDATE app_quarantine_item SET raw_storage_uri = ?, raw_content_hash = ?, "
        "raw_size_bytes = ? WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?) AND raw_storage_uri IS NULL",
        (
            stored.storage_uri,
            stored.content_hash,
            stored.size_bytes,
            item_id,
            workspace_id,
            domain,
        ),
    )
    return {"status": "stored", "idempotent": False}


# --------------------------------------------------------------------------- ── 2.


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
    """Full one-shot provisioning: • Find zone → enable Email Routing → deploy Email Worker → create c"""
    _ensure_tables()
    settings = get_settings()
    public_api_url = (
        settings.public_api_url.rstrip("/")
        if settings.public_api_url
        else str(request.base_url).rstrip("/")
    )
    scan_url = f"{public_api_url}/v1/email/scan"

    # Check for an existing active integration for this zone
    existing = await _async_query(
        "SELECT * FROM cloudflare_integration WHERE workspace_id = ? AND zone_name = ? LIMIT 1",
        (current_user.workspace_id, payload.zone_name),
    )
    api_token = payload.cf_api_token
    if not api_token:
        token_rows = await _async_query(
            "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
            (current_user.workspace_id,),
        )
        if token_rows and token_rows[0].get("api_token"):
            stored_token = token_rows[0]["api_token"]
            api_token = decrypt_secret(
                stored_token,
                configured_key=settings.secret_encryption_key,
                environment=settings.environment,
            )
    if not api_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cloudflare API token is not configured",
        )
    if existing:
        failed_row = existing[0]
        has_remote_resources = all(
            failed_row.get(field) for field in ("zone_id", "account_id", "worker_name")
        )
        if failed_row.get("status") == "error" and not has_remote_resources:
            await _async_query(
                "DELETE FROM cloudflare_integration WHERE id = ? AND workspace_id = ?",
                (failed_row["id"], current_user.workspace_id),
            )
            existing = []
    if existing:
        row = existing[0]
        if row["status"] == "provisioning":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An auto-configuration for {payload.zone_name} is already running in the background. Please wait.",
            )

        now = datetime.now(timezone.utc).isoformat()
        try:
            provisioner = CloudflareProvisioner(api_token=api_token)
            dns_sync_result = await _sync_domain_shield_dns(
                provisioner=provisioner,
                workspace_id=current_user.workspace_id,
                zone_name=payload.zone_name,
                fix_spf=payload.fix_spf,
                fix_dkim=payload.fix_dkim,
                fix_dmarc=payload.fix_dmarc,
            )
        except CloudflareAPIError as exc:
            await _async_query(
                "UPDATE cloudflare_integration SET error_message=?, api_token=?, updated_at=? WHERE id=?",
                (str(exc)[:500], _encrypt_provider_token(api_token), now, row["id"]),
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
                        _encrypt_provider_token(api_token),
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
                        _encrypt_provider_token(api_token),
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
            (_encrypt_provider_token(api_token), now, row["id"]),
        )
        await _async_query(
            """
            INSERT INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workspace_id) DO UPDATE SET
                api_token=excluded.api_token, updated_at=excluded.updated_at
            """,
            (
                current_user.workspace_id,
                _encrypt_provider_token(api_token),
                now,
                now,
            ),
        )
        await _async_query(
            """
            INSERT INTO app_alert_history (
                id, workspace_id, domain, event_type, action_page,
                title, message, is_dismissed, created_at
            ) VALUES (?, ?, ?, 'cloudflare_sync', NULL, ?, ?, 0, ?)
            """,
            (
                str(uuid4()),
                current_user.workspace_id,
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
            _encrypt_provider_token(api_token),
            "",
            "provisioning",
            now,
            now,
        ),
    )

    # Also automatically persist the token into app_cloudflare_config for the workspace
    if api_token:
        await _async_query(
            """
            INSERT INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workspace_id) DO UPDATE SET
                api_token=excluded.api_token, updated_at=excluded.updated_at
            """,
            (
                current_user.workspace_id,
                _encrypt_provider_token(api_token),
                now,
                now,
            ),
        )

    dns_sync_result: dict[str, Any] | None = None
    try:
        dns_sync_result = await _sync_domain_shield_dns(
            provisioner=CloudflareProvisioner(api_token=api_token),
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
            provisioner = CloudflareProvisioner(api_token=api_token)
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
                # DNS health is not gateway provisioning: keep the integration, surface DNS apart.
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
                    INSERT INTO app_domain_shield_status (
                        domain, workspace_id, spf_valid, spf_record, dkim_valid, dkim_record,
                        dmarc_valid, dmarc_record, dmarc_policy, ssl_valid, ssl_days_remaining,
                        reputation_score, score_grade, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 365, ?, ?, ?)
                    ON CONFLICT(domain) DO UPDATE SET
                        workspace_id=excluded.workspace_id, spf_valid=excluded.spf_valid,
                        spf_record=excluded.spf_record, dkim_valid=excluded.dkim_valid,
                        dkim_record=excluded.dkim_record, dmarc_valid=excluded.dmarc_valid,
                        dmarc_record=excluded.dmarc_record, dmarc_policy=excluded.dmarc_policy,
                        ssl_valid=excluded.ssl_valid, ssl_days_remaining=excluded.ssl_days_remaining,
                        reputation_score=excluded.reputation_score, score_grade=excluded.score_grade,
                        updated_at=excluded.updated_at
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
                    id, workspace_id, domain, event_type, action_page,
                    title, message, is_dismissed, created_at
                ) VALUES (?, ?, ?, 'cloudflare_sync', NULL, ?, ?, 0, ?)
                """,
                (
                    str(uuid4()),
                    current_user.workspace_id,
                    payload.zone_name.lower(),
                    "Configuration Cloudflare appliquée",
                    f"{payload.zone_name} est synchronisé avec Cloudflare.",
                    ts,
                ),
            )

            logger.info("Cloudflare provisioning complete for zone %s", payload.zone_name)
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


# --------------------------------------------------------------------------- ── 3.


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


# --------------------------------------------------------------------------- ── 4.


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
            "DELETE FROM app_domain_shield_status WHERE workspace_id = ? OR domain = ?",
            (current_user.workspace_id, row["zone_name"]),
        )

    return {"status": "removed", "zone_name": row["zone_name"]}


# --------------------------------------------------------------------------- ── 5.


class TokenVerifyRequest(BaseModel):
    cf_api_token: str
    zone_name: str


@router.post(
    "/v1/integrations/cloudflare/verify-token",
    response_model=CloudflareTokenVerificationResponse,
    response_model_exclude_unset=True,
)
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


# --------------------------------------------------------------------------- ── 6.


class CloudflareTokenSaveRequest(BaseModel):
    cf_api_token: str = Field(..., description="Cloudflare API token to store")


@router.get(
    "/v1/integrations/cloudflare/token",
    response_model=CloudflareTokenStatusResponse,
)
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
        return {"configured": False}

    rows = await _async_query(
        "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,),
    )
    if rows and rows[0]["api_token"]:
        return {"configured": True}

    return {"configured": bool(integ_rows[0]["api_token"])}


@router.post("/v1/integrations/cloudflare/token", response_model=StatusResponse)
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
        ) from exc

    ts = datetime.now(timezone.utc).isoformat()
    await _async_query(
        """
        INSERT INTO app_cloudflare_config (workspace_id, api_token, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(workspace_id) DO UPDATE SET
            api_token=excluded.api_token, updated_at=excluded.updated_at
        """,
        (
            current_user.workspace_id,
            _encrypt_provider_token(payload.cf_api_token),
            ts,
            ts,
        ),
    )
    return {"status": "saved"}


@router.delete("/v1/integrations/cloudflare/token", response_model=StatusResponse)
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
