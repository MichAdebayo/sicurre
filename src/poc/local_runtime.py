from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime

import bcrypt

from poc.config import get_poc_settings
from poc.pipeline import build_poc_process_env

SETTINGS = get_poc_settings()
POC_AUTH_DB_PATH = SETTINGS.auth_database_path
POC_DATA_DB_PATH = SETTINGS.data_platform_database_path
POC_AUTH_DB_ASYNC_URL = SETTINGS.database_url
POC_DATA_DB_ASYNC_URL = SETTINGS.data_platform_database_url
POC_DATA_DB_SYNC_URL = SETTINGS.data_platform_database_url.replace(
    "sqlite+aiosqlite://", "sqlite://", 1
)
DEFAULT_ADMIN_EMAIL = SETTINGS.admin_email
DEFAULT_ADMIN_PASSWORD = SETTINGS.admin_password
DEFAULT_ADMIN_NAME = SETTINGS.admin_name
DEFAULT_VIEWER_EMAIL = SETTINGS.viewer_email
DEFAULT_VIEWER_PASSWORD = SETTINGS.viewer_password
DEFAULT_VIEWER_NAME = SETTINGS.viewer_name
POC_LOCAL_INFERENCE_API_URL = SETTINGS.inference_api_url
POC_LOCAL_INFERENCE_API_KEY = SETTINGS.inference_api_key


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def demo_accounts() -> list[dict[str, str]]:
    return [
        {
            "role": "Administrateur",
            "email": DEFAULT_ADMIN_EMAIL,
            "display_name": DEFAULT_ADMIN_NAME,
        },
        {
            "role": "Observateur",
            "email": DEFAULT_VIEWER_EMAIL,
            "display_name": DEFAULT_VIEWER_NAME,
        },
    ]


def _seed_accounts() -> list[dict[str, str]]:
    return [
        {
            "role": "Administrateur",
            "email": DEFAULT_ADMIN_EMAIL,
            "password": DEFAULT_ADMIN_PASSWORD,
            "display_name": DEFAULT_ADMIN_NAME,
        },
        {
            "role": "Observateur",
            "email": DEFAULT_VIEWER_EMAIL,
            "password": DEFAULT_VIEWER_PASSWORD,
            "display_name": DEFAULT_VIEWER_NAME,
        },
    ]


def ensure_local_auth_db() -> None:
    if not DEFAULT_ADMIN_PASSWORD or not DEFAULT_VIEWER_PASSWORD:
        raise RuntimeError(
            "SICURRE_POC_ADMIN_PASSWORD et SICURRE_POC_VIEWER_PASSWORD doivent être définis dans .env."
        )

    POC_AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(POC_AUTH_DB_PATH))
    try:
        legacy_event_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'poc_inference_event'"
        ).fetchone()
        app_event_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'app_inference_event'"
        ).fetchone()
        if legacy_event_exists and not app_event_exists:
            conn.execute("ALTER TABLE poc_inference_event RENAME TO app_inference_event")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS poc_user (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT NULL,
                session_token_hash TEXT NULL,
                session_expires_at TEXT NULL
            )
            """)

        user_columns = _table_columns(conn, "poc_user")
        if "session_token_hash" not in user_columns:
            conn.execute("ALTER TABLE poc_user ADD COLUMN session_token_hash TEXT NULL")
        if "session_expires_at" not in user_columns:
            conn.execute("ALTER TABLE poc_user ADD COLUMN session_expires_at TEXT NULL")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_inference_event (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                user_email TEXT NOT NULL,
                context TEXT NOT NULL,
                subject TEXT NOT NULL,
                sender TEXT NOT NULL,
                snippet TEXT NOT NULL,
                safety_verdict TEXT NOT NULL,
                label_verdict TEXT NOT NULL,
                composite_score REAL NOT NULL,
                is_phishing INTEGER NOT NULL,
                delivered_in_smail INTEGER NOT NULL,
                llm_provider TEXT NOT NULL,
                explanation TEXT NOT NULL,
                latency_ms REAL NOT NULL DEFAULT 0,
                used_llm INTEGER NOT NULL DEFAULT 0,
                used_virustotal INTEGER NOT NULL DEFAULT 0,
                inference_source TEXT NOT NULL DEFAULT 'api',
                stage_scores_json TEXT NOT NULL,
                stage_labels_json TEXT NOT NULL,
                stage_breakdown_json TEXT NOT NULL,
                expected_label TEXT NULL
            )
            """)

        event_columns = _table_columns(conn, "app_inference_event")
        if "latency_ms" not in event_columns:
            conn.execute(
                "ALTER TABLE app_inference_event ADD COLUMN latency_ms REAL NOT NULL DEFAULT 0"
            )
        if "used_llm" not in event_columns:
            conn.execute(
                "ALTER TABLE app_inference_event ADD COLUMN used_llm INTEGER NOT NULL DEFAULT 0"
            )
        if "used_virustotal" not in event_columns:
            conn.execute(
                "ALTER TABLE app_inference_event ADD COLUMN used_virustotal INTEGER NOT NULL DEFAULT 0"
            )
        if "inference_source" not in event_columns:
            conn.execute(
                "ALTER TABLE app_inference_event ADD COLUMN inference_source TEXT NOT NULL DEFAULT 'api'"
            )
        if "override_verdict" not in event_columns:
            conn.execute("ALTER TABLE app_inference_event ADD COLUMN override_verdict TEXT NULL")
        if "override_by" not in event_columns:
            conn.execute("ALTER TABLE app_inference_event ADD COLUMN override_by TEXT NULL")
        if "overridden_at" not in event_columns:
            conn.execute("ALTER TABLE app_inference_event ADD COLUMN overridden_at TEXT NULL")
        for account in _seed_accounts():
            row = conn.execute(
                "SELECT id FROM poc_user WHERE email = ?",
                (account["email"],),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE poc_user SET display_name = ?, password_hash = ? WHERE email = ?",
                    (
                        account["display_name"],
                        _hash_password(account["password"]),
                        account["email"],
                    ),
                )
                continue

            conn.execute(
                """
                INSERT INTO poc_user (
                    id,
                    email,
                    display_name,
                    password_hash,
                    role,
                    created_at,
                    last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    account["email"],
                    account["display_name"],
                    _hash_password(account["password"]),
                    "admin" if account["role"] == "Administrateur" else "viewer",
                    datetime.now(UTC).isoformat(),
                    None,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def build_poc_command_env() -> dict[str, str]:
    """Return an isolated environment for local POC subprocesses."""
    return build_poc_process_env(SETTINGS)
