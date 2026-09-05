"""Workspace-scoped false-negative forwarding endpoints."""

from __future__ import annotations

import hashlib
import hmac
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from core.config import Settings, get_settings
from core.rate_limit import limiter
from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.auth import async_query as auth_query
from data_platform.api.routers.app_routes import (
    _extract_dmarc_xml_payload,
    persist_dmarc_report,
)
from data_platform.api.schemas.app_responses import DmarcImportResponse
from data_platform.api.schemas.integration_responses import (
    ReportAddressResponse,
    ReportedEmailIngestResponse,
    ReportedEmailListResponse,
)
from data_platform.services.reported_email import (
    InvalidReportAlias,
    ReportAliasCodec,
    build_reported_email_store,
    report_address,
    sanitized_evidence,
)

router = APIRouter(tags=["reported-email"])


def _dmarc_attachment(raw_message: bytes) -> tuple[str, bytes]:
    """Extract the first valid aggregate DMARC attachment and its domain."""
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    for part in message.walk():
        if part.is_multipart():
            continue
        payload = part.get_payload(decode=True) or b""
        filename = (part.get_filename() or "").lower()
        if not payload or not (
            filename.endswith((".xml", ".xml.gz", ".gz", ".zip"))
            or part.get_content_type()
            in {"application/xml", "text/xml", "application/zip", "application/gzip"}
        ):
            continue
        try:
            xml_payload = _extract_dmarc_xml_payload(payload)
            root = ET.fromstring(xml_payload)
        except (HTTPException, ET.ParseError, OSError):
            continue
        domain = root.findtext("policy_published/domain", "").strip().lower()
        if domain:
            return domain, xml_payload
    raise HTTPException(status_code=400, detail="DMARC report attachment not found")


def _codec(settings: Settings) -> ReportAliasCodec:
    secret = settings.reported_email_alias_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Reported-email aliases are not configured")
    try:
        return ReportAliasCodec(secret)
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="Reported-email aliases are not configured"
        ) from exc


@router.get("/v1/feedback/report-address", response_model=ReportAddressResponse)
async def get_report_address(
    current_user: AuthUser = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    """Return the signed forwarding alias for the authenticated workspace."""
    settings = get_settings()
    token = _codec(settings).encode(current_user.workspace_id)
    return {"address": report_address(settings.reported_email_address, token)}


@router.get("/v1/feedback/reports", response_model=ReportedEmailListResponse)
async def list_reported_emails(
    current_user: AuthUser = Depends(get_current_user),  # noqa: B008
) -> dict[str, list[dict[str, object]]]:
    """List forwarded reports for the authenticated workspace.

    The ingest path wrote these rows and nothing read them back, so a user who
    forwarded a missed phishing email saw no confirmation anywhere in the
    product and had no reason to believe it had worked.

    Metadata only. The ingest pipeline anonymises the message into private R2
    precisely so the forwarded content stops circulating; returning a body here
    would undo that. Scoped on workspace_id like every other tenant route.
    """
    rows = await auth_query(
        "SELECT id, received_at, size_bytes, status FROM app_reported_email "
        "WHERE workspace_id = ? ORDER BY received_at DESC LIMIT 50",
        (current_user.workspace_id,),
    )
    return {
        "items": [
            {
                "id": str(row["id"]),
                "received_at": str(row["received_at"]),
                "size_bytes": int(row["size_bytes"] or 0),
                "status": str(row["status"] or "received"),
            }
            for row in rows
        ]
    }


@router.post(
    "/v1/email/reports/{token}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReportedEmailIngestResponse,
)
@limiter.limit("30/minute")
async def ingest_reported_email(
    request: Request,
    token: str,
    x_sicurre_report_key: str | None = Header(default=None),
) -> dict[str, str | bool]:
    """Accept one Worker-authenticated forwarded message as sanitized evidence."""
    settings = get_settings()
    expected_key = settings.reported_email_ingest_key
    if (
        not expected_key
        or not x_sicurre_report_key
        or not hmac.compare_digest(
            x_sicurre_report_key,
            expected_key,
        )
    ):
        raise HTTPException(status_code=401, detail="Invalid reported-email credential")
    try:
        workspace_id = _codec(settings).decode(token)
    except InvalidReportAlias as exc:
        raise HTTPException(status_code=404, detail="Report alias not found") from exc

    members = await auth_query(
        "SELECT auth_user_id FROM app_workspace_membership WHERE workspace_id = ? "
        "ORDER BY CASE WHEN role = 'owner' THEN 0 ELSE 1 END LIMIT 1",
        (workspace_id,),
    )
    if not members:
        raise HTTPException(status_code=404, detail="Report alias not found")

    raw_message = await request.body()
    if not raw_message:
        raise HTTPException(status_code=400, detail="Empty reported email")
    if len(raw_message) > settings.reported_email_max_message_bytes:
        raise HTTPException(status_code=413, detail="Reported email is too large")

    payload = sanitized_evidence(raw_message)
    content_hash = hashlib.sha256(payload).hexdigest()
    existing = await auth_query(
        "SELECT id FROM app_reported_email WHERE workspace_id = ? AND content_hash = ? LIMIT 1",
        (workspace_id, content_hash),
    )
    if existing:
        return {"status": "accepted", "idempotent": True}
    report_id = str(uuid.uuid4())
    stored = await build_reported_email_store(settings).write(
        workspace_id=workspace_id,
        report_id=report_id,
        payload=payload,
    )
    now = datetime.now(UTC).isoformat()
    try:
        await auth_query(
            "INSERT INTO app_reported_email "
            "(id, workspace_id, workspace_member_user_id, storage_uri, content_hash, "
            "size_bytes, status, received_at) VALUES (?, ?, ?, ?, ?, ?, 'received', ?)",
            (
                report_id,
                workspace_id,
                members[0]["auth_user_id"],
                stored.storage_uri,
                stored.content_hash,
                stored.size_bytes,
                now,
            ),
        )
        await auth_query(
            "INSERT INTO app_feedback "
            "(id, workspace_id, workspace_member_user_id, event_id, feedback_type, "
            "original_verdict, corrected_verdict, reporter_note, created_at) "
            "VALUES (?, ?, ?, NULL, 'false_negative', NULL, 'phishing', ?, ?)",
            (
                str(uuid.uuid4()),
                workspace_id,
                members[0]["auth_user_id"],
                f"reported_email:{report_id}",
                now,
            ),
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            return {"status": "accepted", "idempotent": True}
        raise
    return {"status": "accepted", "idempotent": False}


@router.post(
    "/v1/email/dmarc-reports",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DmarcImportResponse,
)
@limiter.limit("30/minute")
async def ingest_dmarc_email(
    request: Request,
    x_sicurre_report_key: str | None = Header(default=None),
) -> dict[str, str | int]:
    """Accept one Worker-authenticated aggregate DMARC report email."""
    settings = get_settings()
    expected_key = settings.reported_email_ingest_key
    if (
        not expected_key
        or not x_sicurre_report_key
        or not hmac.compare_digest(x_sicurre_report_key, expected_key)
    ):
        raise HTTPException(status_code=401, detail="Invalid reported-email credential")
    raw_message = await request.body()
    if not raw_message:
        raise HTTPException(status_code=400, detail="Empty DMARC report email")
    if len(raw_message) > settings.reported_email_max_message_bytes:
        raise HTTPException(status_code=413, detail="DMARC report email is too large")
    domain, xml_payload = _dmarc_attachment(raw_message)
    integrations = await auth_query(
        "SELECT workspace_id FROM cloudflare_integration "
        "WHERE lower(zone_name) = ? AND status = 'active' "
        "ORDER BY created_at LIMIT 1",
        (domain,),
    )
    if not integrations:
        # Receivers report on every domain that carries our rua, including our
        # own sending domains, which are not customers. That is not an error:
        # 404 made the Worker treat the report as a failed ingest and hand it to
        # the classifier, which quarantined a Google report as phishing.
        return {"status": "ignored", "record_count": 0}
    return await persist_dmarc_report(
        str(integrations[0]["workspace_id"]),
        domain,
        xml_payload,
    )
