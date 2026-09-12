"""Aggregate DMARC reports: import, parse and summarise them per domain."""

from __future__ import annotations

import gzip
import hashlib
import io
import uuid
import xml.etree.ElementTree as ET
import zipfile
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from core.config import get_settings
from core.rate_limit import limiter
from data_platform.api.auth import AuthUser, ensure_runtime_tables, get_current_user
from data_platform.api.schemas.app_responses import DmarcImportResponse, DmarcSummaryResponse
from data_platform.api.workspace_scope import require_workspace_domain
from db.runtime import execute_runtime_query

router = APIRouter(tags=["app-ui-flows"])


def extract_dmarc_xml_payload(payload: bytes) -> bytes:
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
        raise HTTPException(
            status_code=400, detail="DMARC report domain does not match selected domain"
        )

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
        parsed.append(
            {
                "report_org": report_org,
                "report_id": report_id,
                "period_begin": period_begin,
                "period_end": period_end,
                "source_ip": _text_or_none(row, "source_ip") or "unknown",
                "message_count": int(_text_or_none(row, "count") or "0"),
                "disposition": _text_or_none(policy_evaluated, "disposition") or "none",
                "dkim_result": _text_or_none(
                    auth_results.find("dkim") if auth_results is not None else None, "result"
                )
                or "unknown",
                "spf_result": _text_or_none(
                    auth_results.find("spf") if auth_results is not None else None, "result"
                )
                or "unknown",
                "header_from": _text_or_none(identifiers, "header_from") or domain,
            }
        )
    return parsed


@router.get(
    "/v1/domain-shield/{domain}/dmarc-reports",
    response_model=DmarcSummaryResponse,
)
async def get_dmarc_report_summary(
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    await require_workspace_domain(domain, current_user.workspace_id)
    ensure_runtime_tables()
    rows = await execute_runtime_query(
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
    top_sources = await execute_runtime_query(
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


@router.post(
    "/v1/domain-shield/{domain}/dmarc-reports/import",
    response_model=DmarcImportResponse,
)
@limiter.limit("10/minute")
async def import_dmarc_report(
    domain: str,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
):
    await require_workspace_domain(domain, current_user.workspace_id)
    ensure_runtime_tables()
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty DMARC report")
    if len(payload) > get_settings().reported_email_max_message_bytes:
        raise HTTPException(status_code=413, detail="DMARC report is too large")
    return await persist_dmarc_report(
        current_user.workspace_id,
        domain,
        payload,
    )


async def persist_dmarc_report(
    workspace_id: str,
    domain: str,
    payload: bytes,
) -> dict[str, str | int]:
    """Persist one aggregate DMARC report with fingerprint idempotency."""
    ensure_runtime_tables()
    xml_payload = extract_dmarc_xml_payload(payload)
    records = _parse_dmarc_report(xml_payload, domain)
    now = datetime.now(timezone.utc).isoformat()
    imported_count = 0
    report_digest = hashlib.sha256(xml_payload).hexdigest()
    for record_index, record in enumerate(records):
        fingerprint = hashlib.sha256(f"{report_digest}:{record_index}".encode()).hexdigest()
        inserted = await execute_runtime_query(
            """
            INSERT INTO app_dmarc_report_summary (
                id, workspace_id, domain, report_org, report_id, period_begin, period_end,
                source_ip, message_count, disposition, dkim_result, spf_result,
                header_from, report_fingerprint, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, report_fingerprint) DO NOTHING
            RETURNING id
            """,
            (
                str(uuid.uuid4()),
                workspace_id,
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
                fingerprint,
                now,
            ),
        )
        imported_count += 1 if inserted else 0
    return {
        "status": "imported" if imported_count else "already_imported",
        "record_count": imported_count,
    }
