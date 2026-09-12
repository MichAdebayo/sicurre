"""Notification preferences, sender rules and the alert history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from data_platform.api.auth import AuthUser, get_current_user
from data_platform.api.schemas.app_responses import (
    AlertHistoryResponse,
    AlertPreferenceResponse,
    SecurityRuleResponse,
    StatusResponse,
)
from data_platform.api.workspace_scope import owned_domain
from db.runtime import execute_runtime_query

router = APIRouter(tags=["app-ui-flows"])


class AlertPreferenceUpdate(BaseModel):
    email_enabled: bool
    notify_phishing: bool
    notify_domain_shield: bool
    quiet_hours_enabled: bool
    quiet_hours_start: str = Field(default="22:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_end: str = Field(default="07:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Europe/Paris", min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Require a real IANA timezone so quiet hours cannot shift silently."""
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return normalized


class SecurityRuleCreate(BaseModel):
    rule_type: str = Field(pattern="^(whitelist|blocklist)$")
    pattern: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^(?:[^@\s]+@)?(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$",
    )

    @field_validator("pattern", mode="before")
    @classmethod
    def normalize_pattern(cls, value: object) -> object:
        """Store sender and domain rules in their case-insensitive form."""
        return value.strip().lower() if isinstance(value, str) else value


@router.get("/v1/alerts/preferences", response_model=AlertPreferenceResponse)
async def get_alert_preferences(
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT * FROM app_alert_preference WHERE workspace_id = ? "
        "AND lower(domain) = lower(?) LIMIT 1",
        (current_user.workspace_id, active_domain),
    )
    if not rows:
        await execute_runtime_query(
            "INSERT INTO app_alert_preference "
            "(workspace_id, domain, email_enabled, notify_phishing, notify_domain_shield, "
            "quiet_hours_enabled, quiet_hours_start, quiet_hours_end, timezone) "
            "VALUES (?, ?, 1, 1, 1, 0, '22:00', '07:00', 'Europe/Paris')",
            (current_user.workspace_id, active_domain),
        )
        rows = await execute_runtime_query(
            "SELECT * FROM app_alert_preference WHERE workspace_id = ? "
            "AND lower(domain) = lower(?) LIMIT 1",
            (current_user.workspace_id, active_domain),
        )
    r = rows[0]
    return {
        "domain": active_domain,
        "email_enabled": bool(r["email_enabled"]),
        "notify_phishing": bool(r["notify_phishing"]),
        "notify_domain_shield": bool(r["notify_domain_shield"]),
        "quiet_hours_enabled": bool(r["quiet_hours_enabled"]),
        "quiet_hours_start": r["quiet_hours_start"],
        "quiet_hours_end": r["quiet_hours_end"],
        "timezone": r.get("timezone") or "Europe/Paris",
    }


@router.put("/v1/alerts/preferences", response_model=StatusResponse)
async def update_alert_preferences(
    payload: AlertPreferenceUpdate,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    await execute_runtime_query(
        """
        INSERT INTO app_alert_preference
        (workspace_id, domain, email_enabled, notify_phishing, notify_domain_shield,
         quiet_hours_enabled, quiet_hours_start, quiet_hours_end, timezone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(workspace_id, domain) DO UPDATE SET
            email_enabled=excluded.email_enabled,
            notify_phishing=excluded.notify_phishing,
            notify_domain_shield=excluded.notify_domain_shield,
            quiet_hours_enabled=excluded.quiet_hours_enabled,
            quiet_hours_start=excluded.quiet_hours_start,
            quiet_hours_end=excluded.quiet_hours_end,
            timezone=excluded.timezone
        """,
        (
            current_user.workspace_id,
            active_domain,
            1 if payload.email_enabled else 0,
            1 if payload.notify_phishing else 0,
            1 if payload.notify_domain_shield else 0,
            1 if payload.quiet_hours_enabled else 0,
            payload.quiet_hours_start,
            payload.quiet_hours_end,
            payload.timezone,
        ),
    )
    return {"status": "updated"}


@router.get("/v1/alerts/rules", response_model=list[SecurityRuleResponse])
async def list_security_rules(domain: str, current_user: AuthUser = Depends(get_current_user)):
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT * FROM app_security_rule WHERE workspace_id = ? "
        "AND lower(domain) = lower(?) ORDER BY created_at DESC",
        (current_user.workspace_id, active_domain),
    )
    return [
        {
            "id": r["id"],
            "domain": active_domain,
            "rule_type": r["rule_type"],
            "pattern": r["pattern"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.post(
    "/v1/alerts/rules",
    response_model=SecurityRuleResponse,
    response_model_exclude_unset=True,
)
async def create_security_rule(
    payload: SecurityRuleCreate,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    rule_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat() + "Z"
    await execute_runtime_query(
        "INSERT INTO app_security_rule (id, workspace_id, domain, rule_type, pattern, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            rule_id,
            current_user.workspace_id,
            active_domain,
            payload.rule_type,
            payload.pattern,
            now,
        ),
    )
    return {
        "id": rule_id,
        "domain": active_domain,
        "rule_type": payload.rule_type,
        "pattern": payload.pattern,
    }


@router.delete("/v1/alerts/rules/{id}", response_model=StatusResponse)
async def delete_security_rule(
    id: str,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT 1 FROM app_security_rule WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?) LIMIT 1",
        (id, current_user.workspace_id, active_domain),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Rule not found")
    await execute_runtime_query(
        "DELETE FROM app_security_rule WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?)",
        (id, current_user.workspace_id, active_domain),
    )
    return {"status": "deleted"}


@router.get("/v1/alerts/history", response_model=list[AlertHistoryResponse])
async def list_alert_history(domain: str, current_user: AuthUser = Depends(get_current_user)):
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT h.*, CASE WHEN r.alert_id IS NULL THEN 0 ELSE 1 END AS is_read "
        "FROM app_alert_history h LEFT JOIN app_alert_read r "
        "ON r.alert_id = h.id AND r.auth_user_id = ? "
        "WHERE h.workspace_id = ? AND lower(h.domain) = lower(?) "
        "AND h.is_dismissed = 0 ORDER BY h.created_at DESC",
        (current_user.id, current_user.workspace_id, active_domain),
    )
    return [
        {
            "id": r["id"],
            "domain": active_domain,
            "event_type": r.get("event_type") or "system",
            "action_page": r.get("action_page"),
            "title": r["title"],
            "message": r["message"],
            "created_at": r["created_at"],
            "is_read": bool(r["is_read"]),
        }
        for r in rows
    ]


@router.post("/v1/alerts/history/{id}/dismiss", response_model=StatusResponse)
async def dismiss_alert(
    id: str,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT 1 FROM app_alert_history WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?) LIMIT 1",
        (id, current_user.workspace_id, active_domain),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Alert not found")
    await execute_runtime_query(
        "UPDATE app_alert_history SET is_dismissed = 1 WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?)",
        (id, current_user.workspace_id, active_domain),
    )
    return {"status": "dismissed"}


@router.post("/v1/alerts/history/{id}/read", response_model=StatusResponse)
async def mark_alert_read(
    id: str,
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    """Mark one owned, domain-scoped notification as read for this member."""
    active_domain = await owned_domain(domain, current_user)
    rows = await execute_runtime_query(
        "SELECT 1 FROM app_alert_history WHERE id = ? AND workspace_id = ? "
        "AND lower(domain) = lower(?) AND is_dismissed = 0 LIMIT 1",
        (id, current_user.workspace_id, active_domain),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Alert not found")
    await execute_runtime_query(
        "INSERT INTO app_alert_read "
        "(workspace_id, domain, auth_user_id, alert_id, read_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(auth_user_id, alert_id) DO NOTHING",
        (
            current_user.workspace_id,
            active_domain,
            current_user.id,
            id,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return {"status": "read"}


@router.post("/v1/alerts/history/read", response_model=StatusResponse)
async def mark_domain_alerts_read(
    domain: str,
    current_user: AuthUser = Depends(get_current_user),
):
    active_domain = await owned_domain(domain, current_user)
    now = datetime.now(timezone.utc).isoformat()
    await execute_runtime_query(
        "INSERT INTO app_alert_read (workspace_id, domain, auth_user_id, alert_id, read_at) "
        "SELECT ?, ?, ?, id, ? FROM app_alert_history "
        "WHERE workspace_id = ? AND lower(domain) = lower(?) AND is_dismissed = 0 "
        "ON CONFLICT(auth_user_id, alert_id) DO NOTHING",
        (
            current_user.workspace_id,
            active_domain,
            current_user.id,
            now,
            current_user.workspace_id,
            active_domain,
        ),
    )
    return {"status": "read"}
