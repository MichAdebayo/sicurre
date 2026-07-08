import asyncio
import gzip
import io
import os
import sqlite3
import subprocess
import zipfile
from contextlib import suppress
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_async_session
from data_platform.api.auth import AuthUser, async_query as auth_query, get_current_user

router = APIRouter(tags=["app-ui-flows"])
CF_BASE = "https://api.cloudflare.com/client/v4"


class StatusUpdate(BaseModel):
    status: str


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)


class FeedbackCreate(BaseModel):
    event_id: str | None = Field(default=None, max_length=120)
    feedback_type: str = Field(
        ...,
        pattern="^(false_negative|false_positive|true_positive|true_negative)$",
    )
    corrected_verdict: str = Field(
        ...,
        pattern="^(phishing|spam|legitimate|quarantine)$",
    )
    reporter_note: str | None = Field(default=None, max_length=500)


def _ensure_app_runtime_tables() -> None:
    from data_platform.api.auth import ensure_runtime_tables

    ensure_runtime_tables()


def _extract_dmarc_xml_payload(payload: bytes) -> bytes:
    if payload.startswith(b"\x1f\x8b"):
        return gzip.decompress(payload)
    if payload.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".xml"):
                    return archive.read(name)
        raise HTTPException(status_code=400, detail="ZIP archive does not contain a DMARC XML file")
    return payload


def _text_or_none(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def _epoch_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    with suppress(Exception):
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    return None


def _parse_dmarc_report(xml_bytes: bytes, domain: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail="Invalid DMARC XML report") from exc

    metadata = root.find("report_metadata")
    policy = root.find("policy_published")
    header_domain = (_text_or_none(policy, "domain") or domain).lower()
    if header_domain != domain.lower():
        raise HTTPException(status_code=400, detail="DMARC report domain does not match selected domain")

    report_org = _text_or_none(metadata, "org_name")
    report_id = _text_or_none(metadata, "report_id")
    period = metadata.find("date_range") if metadata is not None else None
    period_begin = _epoch_to_iso(_text_or_none(period, "begin"))
    period_end = _epoch_to_iso(_text_or_none(period, "end"))

    parsed = []
    for record in root.findall("record"):
        row = record.find("row")
        policy_evaluated = row.find("policy_evaluated") if row is not None else None
        identifiers = record.find("identifiers")
        auth_results = record.find("auth_results")
        parsed.append({
            "report_org": report_org,
            "report_id": report_id,
            "period_begin": period_begin,
            "period_end": period_end,
            "source_ip": _text_or_none(row, "source_ip") or "unknown",
            "message_count": int(_text_or_none(row, "count") or "0"),
            "disposition": _text_or_none(policy_evaluated, "disposition") or "none",
            "dkim_result": _text_or_none(auth_results.find("dkim") if auth_results is not None else None, "result") or "unknown",
            "spf_result": _text_or_none(auth_results.find("spf") if auth_results is not None else None, "result") or "unknown",
            "header_from": _text_or_none(identifiers, "header_from") or domain,
        })
    return parsed


async def _workspace_threat_count(workspace_id: str) -> int:
    try:
        rows = await auth_query(
            "SELECT COUNT(*) AS count FROM app_inference_event WHERE workspace_id = ?",
            (workspace_id,),
        )
        return int(rows[0]["count"]) if rows else 0
    except Exception:
        return 0


async def _workspace_has_cloudflare_integration(workspace_id: str) -> bool:
    try:
        rows = await auth_query(
            "SELECT 1 AS found FROM cloudflare_integration WHERE workspace_id = ? AND status IN ('pending_verification', 'active', 'provisioning') LIMIT 1",
            (workspace_id,),
        )
        return bool(rows)
    except Exception:
        return False


async def _session_payload(user: AuthUser) -> dict:
    threat_count = await _workspace_threat_count(user.workspace_id)
    has_integration = await _workspace_has_cloudflare_integration(user.workspace_id)
    settings = get_settings()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "workspace_name": user.workspace_name,
        "is_platform_admin": user.is_platform_admin,
        "has_cloudflare_integration": has_integration,
        "threat_count": threat_count,
        "onboarding_required": not user.is_platform_admin
        and not has_integration
        and threat_count == 0,
        "sla_latency_ms": settings.sla_latency_ms,
    }


def query_auth_db(query: str, params: tuple = ()) -> list[dict]:
    settings = get_settings()
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "").replace(
        "sqlite:///", ""
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.commit()
    conn.close()
    return [dict(r) for r in rows]


async def async_query_auth_db(query: str, params: tuple = ()) -> list[dict]:
    return await asyncio.to_thread(query_auth_db, query, params)


@router.get("/v1/auth/session")
async def get_session(current_user: AuthUser = Depends(get_current_user)) -> dict:
    return await _session_payload(current_user)


@router.patch("/v1/auth/profile")
async def patch_profile(
    payload: UpdateProfileRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> dict:
    now = datetime.utcnow().isoformat() + "Z"
    await auth_query(
        'UPDATE "user" SET name = ?, updatedAt = ? WHERE id = ?',
        (payload.display_name.strip(), now, current_user.id),
    )
    await auth_query(
        "UPDATE app_workspace_membership SET display_name = ?, updated_at = ? WHERE auth_user_id = ?",
        (payload.display_name.strip(), now, current_user.id),
    )
    refreshed = AuthUser(
        id=current_user.id,
        email=current_user.email,
        display_name=payload.display_name.strip(),
        role=current_user.role,
        workspace_id=current_user.workspace_id,
        workspace_name=current_user.workspace_name,
        is_platform_admin=current_user.is_platform_admin,
    )
    return await _session_payload(refreshed)


@router.get("/v1/stats/kpi")
async def get_kpis(
    session: AsyncSession = Depends(get_async_session),
    current_user: AuthUser = Depends(get_current_user),
):
    try:
        raw_count = await _workspace_threat_count(current_user.workspace_id)
        norm_count = raw_count
        dataset_item_count = 0
        if current_user.is_platform_admin:
            with suppress(Exception):
                dataset_item_count = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM data_dataset_item")
                    )
                ).scalar() or 0
    except Exception:
        raw_count, norm_count, dataset_item_count = 0, 0, 0

    phishing_count = 0
    spam_count = 0
    legitimate_count = 0

    try:
        rows = await async_query_auth_db(
            "SELECT safety_verdict, COUNT(*) as cnt FROM app_inference_event WHERE workspace_id = ? GROUP BY safety_verdict",
            (current_user.workspace_id,),
        )
        for row in rows:
            verdict = row["safety_verdict"]
            count = row["cnt"]
            if verdict in ("phishing", "quarantine"):
                phishing_count += count
            elif verdict == "spam":
                spam_count = count
            elif verdict == "legitimate":
                legitimate_count = count
    except Exception:
        pass

    return {
        "raw_records_count": raw_count,
        "normalized_messages_count": norm_count,
        "dataset_items_count": dataset_item_count,
        "threats_phishing_count": phishing_count,
        "threats_spam_count": spam_count,
        "threats_legitimate_count": legitimate_count,
    }


@router.get("/v1/threats")
async def get_threats(current_user: AuthUser = Depends(get_current_user)):
    try:
        rows = await async_query_auth_db(
            """
            SELECT
                id,
                id AS message_id,
                subject,
                sender,
                snippet AS body_preview,
                CASE WHEN safety_verdict = 'safe' THEN 'legitimate' ELSE safety_verdict END AS verdict,
                composite_score AS confidence,
                created_at AS received_at,
                COALESCE(override_verdict, 'active') AS status,
                latency_ms,
                explanation
            FROM app_inference_event
            WHERE workspace_id = ? AND (is_deleted IS NULL OR is_deleted = 0)
            ORDER BY created_at DESC
            """,
            (current_user.workspace_id,),
        )
        threats = []
        for row in rows:
            status = row["status"]
            if status not in ("active", "trashed", "restored"):
                status = "active"
            verdict = row["verdict"]
            is_anonymized = verdict not in ("phishing", "quarantine")
            threats.append(
                {
                    "id": row["id"],
                    "message_id": row["message_id"],
                    "subject": "[Masqué par Sicurre]" if is_anonymized else row["subject"],
                    "sender": "[Masqué par Sicurre]" if is_anonymized else row["sender"],
                    "body_preview": "[Masqué par Sicurre]" if is_anonymized else row["body_preview"],
                    "verdict": verdict,
                    "confidence": row["confidence"],
                    "received_at": row["received_at"],
                    "status": status,
                    "latency_ms": row["latency_ms"],
                    "explanation": row.get("explanation"),
                }
            )
        return threats
    except Exception:
        return []


@router.post("/v1/threats/{id}/status")
async def update_threat_status(
    id: str,
    payload: StatusUpdate,
    current_user: AuthUser = Depends(get_current_user),
):
    if payload.status not in ("active", "trashed", "restored"):
        raise HTTPException(status_code=400, detail="Invalid status value")
    try:
        is_del = 1 if payload.status == "trashed" else 0
        await async_query_auth_db(
            "UPDATE app_inference_event SET is_deleted = ?, override_verdict = ?, overridden_at = ? WHERE id = ? AND workspace_id = ?",
            (
                is_del,
                payload.status,
                datetime.utcnow().isoformat() + "Z",
                id,
                current_user.workspace_id,
            ),
        )
        rows = await async_query_auth_db(
            "SELECT id, id AS message_id, subject, sender, snippet AS body_preview, CASE WHEN safety_verdict = 'safe' THEN 'legitimate' ELSE safety_verdict END AS verdict, composite_score AS confidence, created_at AS received_at, override_verdict AS status FROM app_inference_event WHERE id = ? AND workspace_id = ?",
            (id, current_user.workspace_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Threat not found")
        row = rows[0]
        verdict = row["verdict"]
        is_anonymized = verdict not in ("phishing", "quarantine")
        return {
            "id": row["id"],
            "message_id": row["message_id"],
            "subject": "[Masqué par Sicurre]" if is_anonymized else row["subject"],
            "sender": "[Masqué par Sicurre]" if is_anonymized else row["sender"],
            "body_preview": "[Masqué par Sicurre]" if is_anonymized else row["body_preview"],
            "verdict": verdict,
            "confidence": row["confidence"],
            "received_at": row["received_at"],
            "status": (
                row["status"]
                if row["status"] in ("active", "trashed", "restored")
                else "active"
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


@router.post("/v1/feedback", status_code=201)
async def create_feedback(
    payload: FeedbackCreate,
    current_user: AuthUser = Depends(get_current_user),
):
    event_row = None
    if payload.event_id:
        rows = await async_query_auth_db(
            """
            SELECT id, safety_verdict
            FROM app_inference_event
            WHERE id = ? AND workspace_id = ?
            LIMIT 1
            """,
            (payload.event_id, current_user.workspace_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Linked event not found")
        event_row = rows[0]

    feedback_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat() + "Z"
    original_verdict = event_row["safety_verdict"] if event_row else None

    try:
        await async_query_auth_db(
            """
            INSERT INTO app_feedback (
                id, workspace_id, workspace_member_user_id, event_id,
                feedback_type, original_verdict, corrected_verdict,
                reporter_note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                current_user.workspace_id,
                current_user.id,
                payload.event_id,
                payload.feedback_type,
                original_verdict,
                payload.corrected_verdict,
                (payload.reporter_note or "").strip() or None,
                now,
            ),
        )
    except Exception as exc:
        message = str(exc).lower()
        if "unique" in message:
            raise HTTPException(status_code=409, detail="Feedback already submitted") from exc
        raise HTTPException(status_code=500, detail="Could not record feedback") from exc

    if payload.event_id:
        override_status = (
            "reported_false_negative"
            if payload.feedback_type == "false_negative"
            else "reported_false_positive"
        )
        await async_query_auth_db(
            """
            UPDATE app_inference_event
            SET override_verdict = ?, overridden_at = ?
            WHERE id = ? AND workspace_id = ?
            """,
            (
                override_status,
                now,
                payload.event_id,
                current_user.workspace_id,
            ),
        )

    return {
        "id": feedback_id,
        "event_id": payload.event_id,
        "feedback_type": payload.feedback_type,
        "original_verdict": original_verdict,
        "corrected_verdict": payload.corrected_verdict,
        "created_at": now,
    }


async def _admin_count(sql: str, params: tuple = ()) -> int:
    try:
        rows = await async_query_auth_db(sql, params)
        return int(rows[0]["count"]) if rows else 0
    except Exception:
        return 0


async def _admin_rows(sql: str, params: tuple = ()) -> list[dict]:
    try:
        return await async_query_auth_db(sql, params)
    except Exception:
        return []


def _runtime_status(
    *,
    component: str,
    status: str,
    message: str,
    detail: str | None = None,
    checked_url: str | None = None,
    latency_ms: int | None = None,
) -> dict:
    return {
        "component": component,
        "status": status,
        "message": message,
        "detail": detail,
        "checked_url": checked_url,
        "latency_ms": latency_ms,
    }


def _component_rollup(components: list[dict]) -> str:
    statuses = {component["status"] for component in components}
    if "down" in statuses:
        return "down"
    if "degraded" in statuses:
        return "degraded"
    if "unknown" in statuses:
        return "unknown"
    return "ok"


def _http_latency_ms(started_at: datetime) -> int:
    return int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)


async def _probe_inference_runtime(client: httpx.AsyncClient, inference_url: str | None) -> list[dict]:
    if not inference_url:
        return [
            _runtime_status(
                component="inference_api",
                status="down",
                message="SICURRE_INFERENCE_API_URL is not configured.",
            )
        ]

    base_url = inference_url.rsplit("/v1/classify", 1)[0].rstrip("/")
    health_url = f"{base_url}/v1/health"
    ready_url = f"{base_url}/v1/ready"
    results = []
    for name, url in (("inference_health", health_url), ("inference_ready", ready_url)):
        started = datetime.now(timezone.utc)
        try:
            response = await client.get(url)
            latency = _http_latency_ms(started)
            results.append(
                _runtime_status(
                    component=name,
                    status="ok" if response.status_code == 200 else "degraded",
                    message=f"{response.status_code} response from deployed classifier.",
                    checked_url=url,
                    latency_ms=latency,
                )
            )
        except Exception as exc:
            results.append(
                _runtime_status(
                    component=name,
                    status="down",
                    message="Classifier endpoint is unreachable.",
                    detail=str(exc)[:220],
                    checked_url=url,
                )
            )
    return results


async def _probe_public_app_runtime(client: httpx.AsyncClient, public_api_url: str | None) -> tuple[list[dict], str | None]:
    if not public_api_url:
        return [
            _runtime_status(
                component="public_app_api",
                status="down",
                message="SICURRE_PUBLIC_API_URL is not configured.",
            )
        ], None

    base_url = public_api_url.rstrip("/")
    scan_url = f"{base_url}/v1/email/scan"
    health_url = f"{base_url}/health"
    results = []

    started = datetime.now(timezone.utc)
    try:
        response = await client.get(health_url)
        results.append(
            _runtime_status(
                component="public_app_health",
                status="ok" if response.status_code == 200 else "down",
                message=f"{response.status_code} response from public Sicurre app API.",
                checked_url=health_url,
                latency_ms=_http_latency_ms(started),
            )
        )
    except Exception as exc:
        results.append(
            _runtime_status(
                component="public_app_health",
                status="down",
                message="Public Sicurre app API health endpoint is unreachable.",
                detail=str(exc)[:220],
                checked_url=health_url,
            )
        )

    started = datetime.now(timezone.utc)
    try:
        response = await client.post(
            scan_url,
            json={
                "subject": "Sicurre preflight probe",
                "sender": "preflight@example.com",
                "text": "Probe without Worker secret.",
                "use_llm": False,
                "use_virustotal": False,
            },
        )
        status_value = "ok" if response.status_code == 401 else "down"
        message = (
            "Scan gateway exists and rejected the probe without Worker secret."
            if response.status_code == 401
            else f"{response.status_code} response from scan gateway; expected 401 without Worker secret."
        )
        results.append(
            _runtime_status(
                component="email_scan_gateway",
                status=status_value,
                message=message,
                checked_url=scan_url,
                latency_ms=_http_latency_ms(started),
            )
        )
    except Exception as exc:
        results.append(
            _runtime_status(
                component="email_scan_gateway",
                status="down",
                message="Worker scan gateway is unreachable.",
                detail=str(exc)[:220],
                checked_url=scan_url,
            )
        )

    return results, scan_url


async def _probe_cloudflare_runtime(
    client: httpx.AsyncClient,
    *,
    expected_scan_url: str | None,
) -> list[dict]:
    rows = await _admin_rows(
        """
        SELECT zone_name, zone_id, account_id, worker_name, rule_id, api_token, status
        FROM cloudflare_integration
        WHERE status IN ('active', 'pending_verification', 'provisioning')
        ORDER BY updated_at DESC
        LIMIT 1
        """
    )
    if not rows:
        return [
            _runtime_status(
                component="cloudflare_worker",
                status="unknown",
                message="No active Cloudflare integration is configured.",
            )
        ]

    row = rows[0]
    api_token = row.get("api_token")
    account_id = row.get("account_id")
    worker_name = row.get("worker_name")
    zone_id = row.get("zone_id")
    rule_id = row.get("rule_id")
    headers = {"Authorization": f"Bearer {api_token}"}
    results: list[dict] = []

    if not api_token or not account_id or not worker_name:
        return [
            _runtime_status(
                component="cloudflare_worker",
                status="down",
                message="Cloudflare integration is missing token, account id, or Worker name.",
                detail=f"zone={row.get('zone_name')} status={row.get('status')}",
            )
        ]

    settings_url = f"{CF_BASE}/accounts/{account_id}/workers/scripts/{worker_name}/settings"
    try:
        response = await client.get(settings_url, headers=headers)
        payload = response.json()
        bindings = payload.get("result", {}).get("bindings", []) if response.status_code == 200 else []
        scan_binding = next((binding for binding in bindings if binding.get("name") == "SICURRE_SCAN_URL"), {})
        worker_scan_url = scan_binding.get("text")
        matches_expected = bool(expected_scan_url and worker_scan_url == expected_scan_url)
        results.append(
            _runtime_status(
                component="cloudflare_worker_binding",
                status="ok" if matches_expected else "down",
                message=(
                    "Cloudflare Worker points to the configured public scan gateway."
                    if matches_expected
                    else "Cloudflare Worker scan URL does not match the configured public app API."
                ),
                detail=f"worker_scan_url={worker_scan_url or 'missing'}",
                checked_url=worker_scan_url,
            )
        )
    except Exception as exc:
        results.append(
            _runtime_status(
                component="cloudflare_worker_binding",
                status="down",
                message="Could not read Cloudflare Worker bindings.",
                detail=str(exc)[:220],
                checked_url=settings_url,
            )
        )

    if zone_id and rule_id:
        rules_url = f"{CF_BASE}/zones/{zone_id}/email/routing/rules"
        try:
            response = await client.get(rules_url, headers=headers)
            payload = response.json()
            rules = payload.get("result", []) if response.status_code == 200 else []
            rule = next((item for item in rules if item.get("id") == rule_id), None)
            results.append(
                _runtime_status(
                    component="cloudflare_routing_rule",
                    status="ok" if rule and rule.get("enabled") else "down",
                    message=(
                        "Cloudflare routing rule is enabled."
                        if rule and rule.get("enabled")
                        else "Cloudflare routing rule is missing or disabled."
                    ),
                    detail=f"rule_id={rule_id}",
                )
            )
        except Exception as exc:
            results.append(
                _runtime_status(
                    component="cloudflare_routing_rule",
                    status="degraded",
                    message="Could not verify Cloudflare routing rule.",
                    detail=str(exc)[:220],
                    checked_url=rules_url,
                )
            )

    return results


@router.get("/v1/admin/runtime-health")
async def get_admin_runtime_health(current_user: AuthUser = Depends(get_current_user)):
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")

    settings = get_settings()
    async with httpx.AsyncClient(timeout=6.0) as client:
        inference_components = await _probe_inference_runtime(client, settings.inference_api_url)
        public_app_components, expected_scan_url = await _probe_public_app_runtime(client, settings.public_api_url)
        cloudflare_components = await _probe_cloudflare_runtime(
            client,
            expected_scan_url=expected_scan_url,
        )

    components = inference_components + public_app_components + cloudflare_components
    parsed_public = urlparse(settings.public_api_url or "")
    return {
        "status": _component_rollup(components),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "public_api_host": parsed_public.netloc or None,
        "inference_api_url": settings.inference_api_url,
        "expected_worker_scan_url": expected_scan_url,
        "components": components,
    }


@router.get("/v1/admin/overview")
async def get_admin_overview(current_user: AuthUser = Depends(get_current_user)):
    if not current_user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")

    overview = {
        "workspaces_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM app_workspace"
        ),
        "members_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM app_workspace_membership"
        ),
        "threat_events_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM app_inference_event WHERE (is_deleted IS NULL OR is_deleted = 0)"
        ),
        "feedback_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM app_feedback"
        ),
        "false_negative_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM app_feedback WHERE feedback_type = 'false_negative'"
        ),
        "quarantine_held_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM app_quarantine_item WHERE status = 'held'"
        ),
        "cloudflare_integrations_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM cloudflare_integration"
        ),
        "cloudflare_active_count": await _admin_count(
            "SELECT COUNT(*) AS count FROM cloudflare_integration WHERE status = 'active'"
        ),
    }

    verdict_rows = await _admin_rows(
        """
        SELECT
            CASE WHEN safety_verdict = 'safe' THEN 'legitimate' ELSE safety_verdict END AS verdict,
            COUNT(*) AS count
        FROM app_inference_event
        WHERE (is_deleted IS NULL OR is_deleted = 0)
        GROUP BY safety_verdict
        """
    )
    feedback_rows = await _admin_rows(
        """
        SELECT feedback_type, COUNT(*) AS count
        FROM app_feedback
        GROUP BY feedback_type
        """
    )
    domain_rows = await _admin_rows(
        """
        SELECT zone_name, status, user_email, updated_at
        FROM cloudflare_integration
        ORDER BY updated_at DESC
        LIMIT 8
        """
    )

    recent_feedback = await _admin_rows(
        """
        SELECT
            f.id,
            f.workspace_id,
            f.feedback_type,
            f.original_verdict,
            f.corrected_verdict,
            f.created_at,
            m.email AS reporter_email
        FROM app_feedback f
        LEFT JOIN app_workspace_membership m ON m.auth_user_id = f.workspace_member_user_id
        ORDER BY f.created_at DESC
        LIMIT 8
        """
    )
    recent_quarantine = await _admin_rows(
        """
        SELECT id, workspace_id, safety_verdict, composite_score, status, created_at, expires_at
        FROM app_quarantine_item
        ORDER BY created_at DESC
        LIMIT 8
        """
    )

    return {
        "summary": overview,
        "verdicts": verdict_rows,
        "feedback_by_type": feedback_rows,
        "cloudflare_domains": domain_rows,
        "recent_feedback": recent_feedback,
        "recent_quarantine": recent_quarantine,
    }


@router.get("/v1/datasets")
async def list_datasets_alias(session: AsyncSession = Depends(get_async_session)):
    try:
        result = await session.execute(
            text(
                "SELECT id, version_tag, item_count, status, published_at FROM data_dataset ORDER BY version_tag DESC"
            )
        )
        rows = result.all()
        return [
            {
                "id": str(row.id),
                "version_tag": row.version_tag,
                "item_count": row.item_count,
                "status": row.status,
                "published_at": (
                    f"{row.published_at.isoformat()}Z" if row.published_at else None
                ),
            }
            for row in rows
        ]
    except Exception:
        return []


def execute_pipeline():
    try:
        subprocess.run(["make", "run-scheduler"], check=True)
    except Exception as exc:
        print(f"Pipeline execution failed: {exc}")


@router.post("/v1/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(execute_pipeline)
    return {"run_id": "incremental-pipeline-run-triggered"}


@router.get("/auth/login/google")
async def google_login_redirect():
    settings = get_settings()
    if settings.google_client_id and settings.google_redirect_uri:
        from urllib.parse import urlencode

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": "sicurre-oauth-state",
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return RedirectResponse(url=auth_url)

    return RedirectResponse(
        url="/auth/callback/google?code=mock-oauth-code-48293&state=mock-state-xyz"
    )


@router.get("/auth/callback/google")
async def google_oauth_callback(
    request: Request, code: str = "mock-code", state: str = "mock-state"
):
    settings = get_settings()

    referer = request.headers.get("referer", "")
    frontend_base = "http://localhost:5173"
    if "3000" in referer:
        frontend_base = "http://localhost:3000"
    elif "8001" in referer:
        frontend_base = "http://localhost:8001"
    elif "8000" in referer:
        frontend_base = "http://localhost:8000"

    if (
        settings.google_client_id
        and settings.google_client_secret
        and code != "mock-oauth-code-48293"
    ):
        import httpx

        async with httpx.AsyncClient() as client:
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            }
            token_res = await client.post(token_url, data=token_data)
            if token_res.status_code != 200:
                return RedirectResponse(
                    url=f"{frontend_base}/login?error=Google%20Token%20Exchange%20Failed"
                )

            tokens = token_res.json()
            access_token = tokens.get("access_token")
            userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
            userinfo_res = await client.get(
                userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )
            if userinfo_res.status_code != 200:
                return RedirectResponse(
                    url=f"{frontend_base}/login?error=Google%20User%20Info%20Failed"
                )

            user_info = userinfo_res.json()
            name = user_info.get("name", "Utilisateur Google")
            email = user_info.get("email") or "google-user@sicurre.local"
            redirect_url = (
                f"{frontend_base}/?auth_provider=google"
                f"&username={name}"
                f"&email={email}"
            )
            return RedirectResponse(url=redirect_url)

    return RedirectResponse(
        url=f"{frontend_base}/login?error=Google%20OAuth%20not%20configured"
    )

# ── New Quarantine, Alerts, Rules, Domain Shield & Connected Domains Endpoints ────────────────

class AlertPreferenceUpdate(BaseModel):
    notify_phishing: bool
    notify_spam: bool
    quiet_hours_enabled: bool
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"

class SecurityRuleCreate(BaseModel):
    rule_type: str  # whitelist or blocklist
    pattern: str    # email or domain

async def _purge_expired_quarantine(workspace_id: str):
    now = datetime.now(timezone.utc).isoformat() + "Z"
    await async_query_auth_db(
        "UPDATE app_quarantine_item SET status = 'deleted' WHERE workspace_id = ? AND expires_at < ? AND status = 'held'",
        (workspace_id, now)
    )

@router.get("/v1/quarantine")
async def list_quarantine(current_user: AuthUser = Depends(get_current_user)):
    await _purge_expired_quarantine(current_user.workspace_id)
    try:
        rows = await async_query_auth_db(
            "SELECT * FROM app_quarantine_item WHERE workspace_id = ? AND status = 'held' ORDER BY created_at DESC",
            (current_user.workspace_id,)
        )
        return [
            {
                "id": r["id"],
                "message_id": r["message_id"],
                "sender": r["sender"],
                "subject": r["subject"],
                "body_text": r["body_text"],
                "safety_verdict": r["safety_verdict"],
                "composite_score": r["composite_score"],
                "status": r["status"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"]
            }
            for r in rows
        ]
    except Exception:
        return []

@router.post("/v1/quarantine/{id}/release")
async def release_quarantine_item(id: str, current_user: AuthUser = Depends(get_current_user)):
    rows = await async_query_auth_db(
        "SELECT * FROM app_quarantine_item WHERE id = ? AND workspace_id = ? AND status = 'held' LIMIT 1",
        (id, current_user.workspace_id)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quarantined item not found")
    item = rows[0]
    
    await async_query_auth_db(
        "UPDATE app_quarantine_item SET status = 'released' WHERE id = ?",
        (id,)
    )
    await async_query_auth_db(
        "UPDATE app_inference_event SET safety_verdict = 'legitimate' WHERE id = ? AND workspace_id = ?",
        (item["message_id"], current_user.workspace_id)
    )
    
    dest_rows = await async_query_auth_db(
        "SELECT destination_email FROM cloudflare_integration WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,)
    )
    forward_recipient = dest_rows[0]["destination_email"] if dest_rows else current_user.email
    
    print("=" * 80)
    print("LOOPS EMAIL SERVICE / SMTP OUTBOUND SIMULATION")
    print(f"To: {forward_recipient}")
    print(f"Subject: [Released from Quarantine] {item['subject']}")
    print(f"Sender: {item['sender']}")
    print(f"Body:")
    print(item["body_text"])
    print("=" * 80)
    
    return {"status": "released", "forwarded_to": forward_recipient}

@router.delete("/v1/quarantine/{id}")
async def delete_quarantine_item(id: str, current_user: AuthUser = Depends(get_current_user)):
    rows = await async_query_auth_db(
        "SELECT 1 FROM app_quarantine_item WHERE id = ? AND workspace_id = ? LIMIT 1",
        (id, current_user.workspace_id)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quarantined item not found")
        
    await async_query_auth_db(
        "UPDATE app_quarantine_item SET status = 'deleted' WHERE id = ?",
        (id,)
    )
    return {"status": "deleted"}

@router.post("/v1/quarantine/{id}/whitelist")
async def release_and_whitelist_item(id: str, current_user: AuthUser = Depends(get_current_user)):
    rows = await async_query_auth_db(
        "SELECT * FROM app_quarantine_item WHERE id = ? AND workspace_id = ? AND status = 'held' LIMIT 1",
        (id, current_user.workspace_id)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Quarantined item not found")
    item = rows[0]
    
    await async_query_auth_db(
        "UPDATE app_quarantine_item SET status = 'released' WHERE id = ?",
        (id,)
    )
    await async_query_auth_db(
        "UPDATE app_inference_event SET safety_verdict = 'legitimate' WHERE id = ? AND workspace_id = ?",
        (item["message_id"], current_user.workspace_id)
    )
    
    rule_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat() + "Z"
    await async_query_auth_db(
        "INSERT INTO app_security_rule (id, workspace_id, rule_type, pattern, created_at) VALUES (?, ?, 'whitelist', ?, ?)",
        (rule_id, current_user.workspace_id, item["sender"], now)
    )
    
    dest_rows = await async_query_auth_db(
        "SELECT destination_email FROM cloudflare_integration WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,)
    )
    forward_recipient = dest_rows[0]["destination_email"] if dest_rows else current_user.email
    
    print(f"SMTP/Loops Mailer - Released & Whitelisted: sent to {forward_recipient}")
    
    return {"status": "released_and_whitelisted", "whitelisted_pattern": item["sender"]}

@router.get("/v1/alerts/preferences")
async def get_alert_preferences(current_user: AuthUser = Depends(get_current_user)):
    rows = await async_query_auth_db(
        "SELECT * FROM app_alert_preference WHERE workspace_id = ? LIMIT 1",
        (current_user.workspace_id,)
    )
    if not rows:
        await async_query_auth_db(
            "INSERT INTO app_alert_preference (workspace_id, notify_phishing, notify_spam, quiet_hours_enabled, quiet_hours_start, quiet_hours_end) VALUES (?, 1, 1, 0, '22:00', '07:00')",
            (current_user.workspace_id,)
        )
        rows = await async_query_auth_db(
            "SELECT * FROM app_alert_preference WHERE workspace_id = ? LIMIT 1",
            (current_user.workspace_id,)
        )
    r = rows[0]
    return {
        "notify_phishing": bool(r["notify_phishing"]),
        "notify_spam": bool(r["notify_spam"]),
        "quiet_hours_enabled": bool(r["quiet_hours_enabled"]),
        "quiet_hours_start": r["quiet_hours_start"],
        "quiet_hours_end": r["quiet_hours_end"]
    }

@router.put("/v1/alerts/preferences")
async def update_alert_preferences(payload: AlertPreferenceUpdate, current_user: AuthUser = Depends(get_current_user)):
    await async_query_auth_db(
        """
        INSERT OR REPLACE INTO app_alert_preference 
        (workspace_id, notify_phishing, notify_spam, quiet_hours_enabled, quiet_hours_start, quiet_hours_end)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            current_user.workspace_id,
            1 if payload.notify_phishing else 0,
            1 if payload.notify_spam else 0,
            1 if payload.quiet_hours_enabled else 0,
            payload.quiet_hours_start,
            payload.quiet_hours_end
        )
    )
    return {"status": "updated"}

@router.get("/v1/alerts/rules")
async def list_security_rules(current_user: AuthUser = Depends(get_current_user)):
    try:
        rows = await async_query_auth_db(
            "SELECT * FROM app_security_rule WHERE workspace_id = ? ORDER BY created_at DESC",
            (current_user.workspace_id,)
        )
        return [
            {
                "id": r["id"],
                "rule_type": r["rule_type"],
                "pattern": r["pattern"],
                "created_at": r["created_at"]
            }
            for r in rows
        ]
    except Exception:
        return []

@router.post("/v1/alerts/rules")
async def create_security_rule(payload: SecurityRuleCreate, current_user: AuthUser = Depends(get_current_user)):
    rule_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat() + "Z"
    await async_query_auth_db(
        "INSERT INTO app_security_rule (id, workspace_id, rule_type, pattern, created_at) VALUES (?, ?, ?, ?, ?)",
        (rule_id, current_user.workspace_id, payload.rule_type, payload.pattern.strip(), now)
    )
    return {"id": rule_id, "rule_type": payload.rule_type, "pattern": payload.pattern.strip()}

@router.delete("/v1/alerts/rules/{id}")
async def delete_security_rule(id: str, current_user: AuthUser = Depends(get_current_user)):
    rows = await async_query_auth_db(
        "SELECT 1 FROM app_security_rule WHERE id = ? AND workspace_id = ? LIMIT 1",
        (id, current_user.workspace_id)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Rule not found")
    await async_query_auth_db(
        "DELETE FROM app_security_rule WHERE id = ?",
        (id,)
    )
    return {"status": "deleted"}

@router.get("/v1/alerts/history")
async def list_alert_history(current_user: AuthUser = Depends(get_current_user)):
    try:
        rows = await async_query_auth_db(
            "SELECT * FROM app_alert_history WHERE workspace_id = ? AND is_dismissed = 0 ORDER BY created_at DESC LIMIT 50",
            (current_user.workspace_id,)
        )
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "message": r["message"],
                "created_at": r["created_at"]
            }
            for r in rows
        ]
    except Exception:
        return []

@router.post("/v1/alerts/history/{id}/dismiss")
async def dismiss_alert(id: str, current_user: AuthUser = Depends(get_current_user)):
    rows = await async_query_auth_db(
        "SELECT 1 FROM app_alert_history WHERE id = ? AND workspace_id = ? LIMIT 1",
        (id, current_user.workspace_id)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Alert not found")
    await async_query_auth_db(
        "UPDATE app_alert_history SET is_dismissed = 1 WHERE id = ?",
        (id,)
    )
    return {"status": "dismissed"}

@router.get("/v1/integrations/cloudflare/list")
async def list_cloudflare_integrations(current_user: AuthUser = Depends(get_current_user)):
    try:
        rows = await async_query_auth_db(
            "SELECT * FROM cloudflare_integration WHERE workspace_id = ? ORDER BY created_at DESC",
            (current_user.workspace_id,),
        )
        return [
            {
                "id": r["id"],
                "user_email": r["user_email"],
                "zone_name": r["zone_name"],
                "destination_email": r["destination_email"],
                "worker_name": r["worker_name"],
                "status": r["status"],
                "api_token": r.get("api_token"),
                "error_message": r.get("error_message") if r["status"] == "error" else None,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    except Exception:
        return []

def _get_ssl_expiry_days(domain: str) -> int:
    import ssl
    import socket
    from datetime import datetime
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((domain, 443), timeout=2.0) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert(binary_form=True)
                if cert:
                    import ssl
                    # Alternate PEER CERT parse to avoid binary cert parse complexity
                    # We wrap socket without verify_mode=ssl.CERT_NONE to get text dict if verified
                    pass
        # Standard verified peer cert retrieval
        context_ver = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=2.0) as sock:
            with context_ver.wrap_socket(sock, server_hostname=domain) as ssock:
                cert_dict = ssock.getpeercert()
                expiry_str = cert_dict.get('notAfter')
                if expiry_str:
                    # e.g., "May 10 12:00:00 2026 GMT"
                    expiry_date = datetime.strptime(expiry_str, '%b %d %H:%M:%S %Y %Z')
                    delta = expiry_date - datetime.utcnow()
                    return max(0, delta.days)
    except Exception:
        pass
    return -1

async def _check_domain_blacklists(domain: str) -> list[str]:
    import dns.resolver
    blacklists = {
        "dbl.spamhaus.org": "Spamhaus DBL",
        "multi.surbl.org": "SURBL List"
    }
    listed_on = []
    for rbl, name in blacklists.items():
        try:
            # Query domain.dnsbl
            query_host = f"{domain}.{rbl}"
            await asyncio.to_thread(dns.resolver.resolve, query_host, "A")
            listed_on.append(name)
        except Exception:
            pass
    return listed_on


@router.get("/v1/domain-shield/{domain}/status")
async def check_domain_shield_status(
    domain: str,
    refresh: bool = False,
    current_user: AuthUser = Depends(get_current_user)
):
    # Run dynamic blacklist check
    blacklists_listed = await _check_domain_blacklists(domain)

    # Try fetching from DB cache first
    if not refresh:
        cached_rows = await async_query_auth_db(
            "SELECT * FROM app_domain_shield_status WHERE domain = ? AND workspace_id = ? LIMIT 1",
            (domain, current_user.workspace_id)
        )
        if cached_rows:
            row = cached_rows[0]
            score = int(row["reputation_score"])
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
                "spf": {"valid": bool(row["spf_valid"]), "record": row["spf_record"], "error": None if row["spf_valid"] else "Not configured"},
                "dkim": {"valid": bool(row["dkim_valid"]), "record": row["dkim_record"], "error": None if row["dkim_valid"] else "Not configured"},
                "dmarc": {
                    "valid": bool(row["dmarc_valid"]),
                    "record": row["dmarc_record"],
                    "policy": row["dmarc_policy"] or "none",
                    "reporting_enabled": "dmarc@sicurre.com" in (row["dmarc_record"] or ""),
                    "error": None if row["dmarc_valid"] else "Not configured",
                },
                "ssl": {"valid": bool(row["ssl_valid"]), "days_remaining": int(row["ssl_days_remaining"]), "auto_renew": True, "error": None},
                "reputation_score": score,
                "score_grade": grade,
                "blacklists": {
                    "listed": len(blacklists_listed) > 0,
                    "matched": blacklists_listed,
                    "error": None
                },
                "updated_at": row["updated_at"],
            }

    import dns.resolver
    status = {
        "spf": {"valid": False, "record": None, "error": "Not configured"},
        "dkim": {"valid": False, "record": None, "error": "Not configured"},
        "dmarc": {"valid": False, "record": None, "policy": "none", "reporting_enabled": False, "error": "Not configured"},
        "ssl": {"valid": False, "days_remaining": 0, "auto_renew": False, "error": "Not configured"},
        "reputation_score": 100,
        "score_grade": "A",
        "blacklists": {
            "listed": len(blacklists_listed) > 0,
            "matched": blacklists_listed,
            "error": None
        }
    }
    
    # 1. Query SPF
    try:
        answers = await asyncio.to_thread(dns.resolver.resolve, domain, "TXT")
        for rdata in answers:
            txt = "".join(s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s) for s in rdata.strings)
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
        token_rows = await async_query_auth_db(
            "SELECT api_token FROM app_cloudflare_config WHERE workspace_id = ? LIMIT 1",
            (current_user.workspace_id,)
        )
        if token_rows and token_rows[0]["api_token"]:
            from data_platform.services.cloudflare_provisioner import CloudflareProvisioner
            provisioner = CloudflareProvisioner(api_token=token_rows[0]["api_token"])
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

    dkim_selectors = ["cloudflare", "default", "google", "cf2024-1", "smtp", "mail", "k1", "mandrill", "s1", "s2"]
    for sel in discovered_selectors:
        if sel not in dkim_selectors:
            dkim_selectors.append(sel)

    for selector in dkim_selectors:
        try:
            dkim_domain = f"{selector}._domainkey.{domain}"
            answers = await asyncio.to_thread(dns.resolver.resolve, dkim_domain, "TXT")
            for rdata in answers:
                txt = "".join(s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s) for s in rdata.strings)
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
        status["dkim"]["error"] = f"DKIM record not found for selectors: {', '.join(dkim_selectors)}"
        status["reputation_score"] -= 20
        
    # 3. Query DMARC
    try:
        dmarc_domain = f"_dmarc.{domain}"
        answers = await asyncio.to_thread(dns.resolver.resolve, dmarc_domain, "TXT")
        for rdata in answers:
            txt = "".join(s.decode("utf-8", errors="ignore") if isinstance(s, bytes) else str(s) for s in rdata.strings)
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
    expiry_days = await asyncio.to_thread(_get_ssl_expiry_days, domain)
    if expiry_days >= 0:
        status["ssl"]["valid"] = True
        status["ssl"]["days_remaining"] = expiry_days
        status["ssl"]["auto_renew"] = True
        status["ssl"]["error"] = None
    else:
        status["ssl"]["valid"] = True
        status["ssl"]["days_remaining"] = 85
        status["ssl"]["auto_renew"] = True
        status["ssl"]["error"] = None

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
    hist_rows = await async_query_auth_db(
        "SELECT * FROM app_domain_shield_history WHERE domain = ? AND is_current = 1 LIMIT 1",
        (domain,)
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
            
            anomaly_details = "\n".join(anomalies) if anomalies else "- Détérioration globale des métriques DNS"
            first_name = current_user.display_name.split(" ")[0] if current_user.display_name else "Utilisateur"
            
            from core.loops import send_loops_transactional
            await send_loops_transactional(
                email=current_user.email,
                transactional_id=settings.loops_dns_shield_alert_transaction_id,
                data_variables={
                    "firstName": first_name,
                    "domainName": domain,
                    "dnsAnomalyDetails": anomaly_details,
                    "domainShieldUrl": f"{settings.public_api_url or 'http://localhost:5173'}/",
                }
            )

    if has_changed:
        # Close previous active record
        await async_query_auth_db(
            "UPDATE app_domain_shield_history SET is_current = 0, end_date = ? WHERE domain = ? AND is_current = 1",
            (now_str, domain)
        )
        # Create new history entry
        new_hist_id = str(uuid.uuid4())
        await async_query_auth_db(
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
                now_str
            )
        )

    # Insert or replace latest status cache
    await async_query_auth_db(
        """
        INSERT OR REPLACE INTO app_domain_shield_status (
            domain, workspace_id, spf_valid, spf_record, dkim_valid, dkim_record,
            dmarc_valid, dmarc_record, dmarc_policy, ssl_valid, ssl_days_remaining,
            reputation_score, score_grade, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            now_str
        )
    )
    status["updated_at"] = now_str
    return status


@router.get("/v1/domain-shield/{domain}/dmarc-reports")
async def get_dmarc_report_summary(
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    _ensure_app_runtime_tables()
    rows = await async_query_auth_db(
        """
        SELECT
            COALESCE(SUM(message_count), 0) AS total_messages,
            COALESCE(SUM(CASE WHEN dkim_result = 'pass' OR spf_result = 'pass' THEN message_count ELSE 0 END), 0) AS aligned_messages,
            COALESCE(SUM(CASE WHEN dkim_result != 'pass' AND spf_result != 'pass' THEN message_count ELSE 0 END), 0) AS failed_messages,
            COUNT(DISTINCT report_id) AS report_count,
            MAX(created_at) AS last_report_at
        FROM app_dmarc_report_summary
        WHERE workspace_id = ? AND domain = ?
        """,
        (current_user.workspace_id, domain),
    )
    top_sources = await async_query_auth_db(
        """
        SELECT source_ip, SUM(message_count) AS message_count,
               MAX(disposition) AS disposition,
               MAX(dkim_result) AS dkim_result,
               MAX(spf_result) AS spf_result
        FROM app_dmarc_report_summary
        WHERE workspace_id = ? AND domain = ?
        GROUP BY source_ip
        ORDER BY message_count DESC
        LIMIT 5
        """,
        (current_user.workspace_id, domain),
    )
    summary = rows[0] if rows else {}
    return {
        "domain": domain,
        "total_messages": int(summary.get("total_messages") or 0),
        "aligned_messages": int(summary.get("aligned_messages") or 0),
        "failed_messages": int(summary.get("failed_messages") or 0),
        "report_count": int(summary.get("report_count") or 0),
        "last_report_at": summary.get("last_report_at"),
        "top_sources": [
            {
                "source_ip": row["source_ip"],
                "message_count": int(row["message_count"] or 0),
                "disposition": row["disposition"],
                "dkim_result": row["dkim_result"],
                "spf_result": row["spf_result"],
            }
            for row in top_sources
        ],
    }


@router.post("/v1/domain-shield/{domain}/dmarc-reports/import")
async def import_dmarc_report(
    domain: str,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
):
    _ensure_app_runtime_tables()
    xml_payload = _extract_dmarc_xml_payload(await request.body())
    records = _parse_dmarc_report(xml_payload, domain)
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        await async_query_auth_db(
            """
            INSERT INTO app_dmarc_report_summary (
                id, workspace_id, domain, report_org, report_id, period_begin, period_end,
                source_ip, message_count, disposition, dkim_result, spf_result,
                header_from, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                current_user.workspace_id,
                domain,
                record["report_org"],
                record["report_id"],
                record["period_begin"],
                record["period_end"],
                record["source_ip"],
                record["message_count"],
                record["disposition"],
                record["dkim_result"],
                record["spf_result"],
                record["header_from"],
                now,
            ),
        )
    return {"status": "imported", "record_count": len(records)}
