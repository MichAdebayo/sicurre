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
                    str(uuid4()),
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
                str(uuid4()),
                now,
                integration["user_email"],
                integration.get("workspace_id"),
                integration.get("workspace_member_user_id"),
                "cloudflare_intercept",
                payload.subject[:240],
                payload.sender[:200],
                payload.text[:240],
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
        "SELECT id, status FROM cloudflare_integration WHERE workspace_id = ? AND zone_name = ? LIMIT 1",
        (current_user.workspace_id, payload.zone_name),
    )
    if existing and existing[0]["status"] in (
        "active",
        "pending_verification",
        "provisioning",
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An integration for {payload.zone_name} already exists (status: {existing[0]['status']}). Tear it down first.",
        )

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
             destination_email, shared_secret_hash, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            "",
            "provisioning",
            now,
            now,
        ),
    )

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
    return {
        "id": row["id"],
        "user_email": row["user_email"],
        "zone_name": row["zone_name"],
        "destination_email": row["destination_email"],
        "worker_name": row["worker_name"],
        "status": row["status"],
        "error_message": row.get("error_message"),
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
