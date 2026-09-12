"""The two routes the Cloudflare Email Worker calls with the shared secret.

- ``POST /v1/email/scan``: run the workspace rules, the inference service and
  the quarantine decision for one message, record the event and return the
  verdict.
- ``PUT /v1/email/quarantine/{item_id}/content``: deposit the original MIME
  of a held message in custody.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.config import get_settings
from core.inference_client import get_inference_client
from core.loops import send_loops_transactional
from core.mime_headers import decode_mime_header, extract_mime_body
from core.rate_limit import limiter
from core.scan_metrics import observe_scan, observe_scan_failure, observe_stage
from data_platform.api.auth import ensure_runtime_tables
from data_platform.api.schemas.integration_responses import QuarantineCustodyResponse
from data_platform.cleaning.normalization import anonymize_pii
from data_platform.services.email_context import derive_email_context
from data_platform.services.notification_policy import notification_is_allowed
from data_platform.services.quarantine_storage import build_quarantine_store
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations"])


async def _async_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return await execute_runtime_query(sql, params)


async def _timed_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Same as _async_query, but attributed to the "database" scan stage."""
    # Delegates through _async_query rather than calling the engine directly so
    # the existing module-level test seam keeps working.
    with observe_stage("database"):
        return await _async_query(sql, params)


def _alert_domain(recipient: str | None, zone_name: str | None) -> str:
    """Name the domain the message was addressed to, not the one that scanned it.

    A single Worker can serve several zones behind one shared secret, so the
    integration it resolves to is not necessarily the recipient's domain. A
    DMARC report for mail.sicurre.com was announced to the customer as "votre
    domaine vinse.app" because the alert used the integration. Older Workers do
    not send a recipient, so the zone remains the fallback.
    """
    local, at, host = (recipient or "").rpartition("@")
    # rpartition returns the whole string as the tail when there is no "@", so
    # a malformed recipient would otherwise be shown to the customer as if it
    # were a domain.
    domain = host.strip().lower() if at and local else ""
    return domain or str(zone_name or "").strip().lower() or "votre domaine"


class EmailScanRequest(BaseModel):
    message_id: str | None = Field(default=None, max_length=500)
    subject: str = Field(default="", max_length=500)
    sender: str = Field(default="", max_length=200)
    #: Envelope recipient. One Worker can serve several zones, so the
    #: integration resolved from its shared secret does not identify the domain
    #: the message was actually sent to. Optional: older Workers omit it.
    recipient: str = Field(default="", max_length=200)
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
    ensure_runtime_tables()

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
    alert_domain = _alert_domain(payload.recipient, integration.get("zone_name"))

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
                        "domainName": alert_domain,
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

    # event_id is a uuid5 of workspace:zone:message_id, so one message scanned
    # twice - two rua addresses on one DMARC record, or a retry - lands on one
    # row. A later, milder scan must not soften a verdict that already
    # quarantined the message, or the journal contradicts the quarantine.
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
            ON CONFLICT(id) DO UPDATE SET
                safety_verdict=excluded.safety_verdict,
                label_verdict=excluded.label_verdict,
                composite_score=excluded.composite_score,
                is_phishing=excluded.is_phishing,
                subject=excluded.subject, sender=excluded.sender, snippet=excluded.snippet,
                explanation=excluded.explanation, llm_provider=excluded.llm_provider,
                latency_ms=excluded.latency_ms, model_version=excluded.model_version,
                model_revision=excluded.model_revision
            WHERE app_inference_event.safety_verdict NOT IN ('phishing', 'quarantine')
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
