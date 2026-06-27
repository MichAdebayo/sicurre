from __future__ import annotations

import asyncio
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from core.config import get_settings
from core.security import AuthenticatedPrincipal, require_authenticated_principal

PLATFORM_ADMIN_ROLE = "admin"
WORKSPACE_OWNER_ROLE = "owner"


@dataclass(slots=True)
class AuthUser:
    id: str
    email: str
    display_name: str
    role: str
    workspace_id: str
    workspace_name: str
    is_platform_admin: bool


def _db_path() -> str:
    settings = get_settings()
    return settings.database_url.replace("sqlite+aiosqlite:///", "").replace(
        "sqlite:///", ""
    )


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def ensure_runtime_tables() -> None:
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_workspace (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                owner_auth_user_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_workspace_membership (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                auth_user_id TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(workspace_id) REFERENCES app_workspace(id) ON DELETE CASCADE,
                UNIQUE(workspace_id, auth_user_id)
            )
            """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_app_workspace_membership_workspace_id ON app_workspace_membership(workspace_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_app_workspace_membership_email ON app_workspace_membership(email)"
        )

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "poc_inference_event" in tables and "app_inference_event" not in tables:
            conn.execute(
                "ALTER TABLE poc_inference_event RENAME TO app_inference_event"
            )

        refreshed_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "app_inference_event" in refreshed_tables:
            event_columns = _table_columns(conn, "app_inference_event")
            if "workspace_id" not in event_columns:
                conn.execute(
                    "ALTER TABLE app_inference_event ADD COLUMN workspace_id TEXT NULL"
                )
            if "workspace_member_user_id" not in event_columns:
                conn.execute(
                    "ALTER TABLE app_inference_event ADD COLUMN workspace_member_user_id TEXT NULL"
                )

        if "cloudflare_integration" in refreshed_tables:
            cf_columns = _table_columns(conn, "cloudflare_integration")
            if "workspace_id" not in cf_columns:
                conn.execute(
                    "ALTER TABLE cloudflare_integration ADD COLUMN workspace_id TEXT NULL"
                )
            if "workspace_member_user_id" not in cf_columns:
                conn.execute(
                    "ALTER TABLE cloudflare_integration ADD COLUMN workspace_member_user_id TEXT NULL"
                )

        # ── 1. Security Rules ────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_security_rule (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_app_security_rule_workspace_id ON app_security_rule(workspace_id)")

        # ── 2. Alert Preferences ─────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_alert_preference (
                workspace_id TEXT PRIMARY KEY,
                notify_phishing INTEGER NOT NULL DEFAULT 1,
                notify_spam INTEGER NOT NULL DEFAULT 1,
                quiet_hours_enabled INTEGER NOT NULL DEFAULT 0,
                quiet_hours_start TEXT NOT NULL DEFAULT '22:00',
                quiet_hours_end TEXT NOT NULL DEFAULT '07:00'
            )
        """)

        # ── 3. Alert History ────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_alert_history (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_dismissed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_app_alert_history_workspace_id ON app_alert_history(workspace_id)")

        # ── 4. Quarantine Items ──────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_quarantine_item (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                subject TEXT NOT NULL,
                body_text TEXT NOT NULL,
                safety_verdict TEXT NOT NULL,
                composite_score REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'held',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_app_quarantine_item_workspace_id ON app_quarantine_item(workspace_id)")

        conn.commit()
    finally:
        conn.close()


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    ensure_runtime_tables()
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


async def async_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_query, sql, params)


def _slugify_workspace_name(display_name: str, email: str, auth_user_id: str) -> str:
    base_source = display_name.strip() or email.split("@", 1)[0]
    slug = re.sub(r"[^a-z0-9]+", "-", base_source.lower()).strip("-")
    if not slug:
        slug = "workspace"
    return f"{slug}-{auth_user_id[:8]}"


def _workspace_name(display_name: str, email: str) -> str:
    label = display_name.strip() or email.split("@", 1)[0]
    return f"{label} Workspace"


async def _get_better_auth_user(principal: AuthenticatedPrincipal) -> dict[str, Any]:
    rows = await async_query(
        'SELECT id, name, email FROM "user" WHERE id = ? LIMIT 1',
        (principal.subject,),
    )
    if not rows and principal.email:
        rows = await async_query(
            'SELECT id, name, email FROM "user" WHERE email = ? LIMIT 1',
            (principal.email.lower(),),
        )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user record not found",
        )
    return rows[0]


async def _backfill_workspace_owned_rows(
    workspace_id: str,
    auth_user_id: str,
    email: str,
) -> None:
    await async_query(
        "UPDATE app_inference_event SET workspace_id = ?, workspace_member_user_id = ? WHERE (workspace_id IS NULL OR workspace_id = '') AND user_email = ?",
        (workspace_id, auth_user_id, email),
    )
    await async_query(
        "UPDATE cloudflare_integration SET workspace_id = ?, workspace_member_user_id = ? WHERE (workspace_id IS NULL OR workspace_id = '') AND user_email = ?",
        (workspace_id, auth_user_id, email),
    )


async def _ensure_workspace_membership(
    principal: AuthenticatedPrincipal,
) -> AuthUser:
    user_row = await _get_better_auth_user(principal)
    auth_user_id = str(user_row["id"])
    email = str(user_row.get("email") or principal.email or "").strip().lower()
    display_name = str(
        user_row.get("name") or principal.display_name or email.split("@", 1)[0]
    ).strip()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user email missing",
        )

    membership_rows = await async_query(
        """
        SELECT
            m.workspace_id,
            m.role AS membership_role,
            w.name AS workspace_name
        FROM app_workspace_membership m
        JOIN app_workspace w ON w.id = m.workspace_id
        WHERE m.auth_user_id = ?
        LIMIT 1
        """,
        (auth_user_id,),
    )

    now = datetime.now(timezone.utc).isoformat()
    if not membership_rows:
        workspace_id = str(uuid.uuid4())
        membership_id = str(uuid.uuid4())
        workspace_name = _workspace_name(display_name, email)
        workspace_slug = _slugify_workspace_name(display_name, email, auth_user_id)
        await async_query(
            """
            INSERT INTO app_workspace (id, name, slug, owner_auth_user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                workspace_name,
                workspace_slug,
                auth_user_id,
                now,
                now,
            ),
        )
        await async_query(
            """
            INSERT INTO app_workspace_membership (id, workspace_id, auth_user_id, email, display_name, role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                membership_id,
                workspace_id,
                auth_user_id,
                email,
                display_name,
                WORKSPACE_OWNER_ROLE,
                now,
                now,
            ),
        )
        membership_role = WORKSPACE_OWNER_ROLE
    else:
        workspace_id = str(membership_rows[0]["workspace_id"])
        workspace_name = str(membership_rows[0]["workspace_name"])
        membership_role = str(membership_rows[0]["membership_role"])
        await async_query(
            "UPDATE app_workspace_membership SET email = ?, display_name = ?, updated_at = ? WHERE auth_user_id = ?",
            (email, display_name, now, auth_user_id),
        )

    await _backfill_workspace_owned_rows(workspace_id, auth_user_id, email)

    settings = get_settings()
    return AuthUser(
        id=auth_user_id,
        email=email,
        display_name=display_name,
        role=membership_role,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        is_platform_admin=email in settings.platform_admin_email_set,
    )


async def get_current_user(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> AuthUser:
    _ = request
    return await _ensure_workspace_membership(principal)
