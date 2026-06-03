from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
LOCAL_DATA_DIR = ROOT_DIR / "data" / "local"

POC_AUTH_DB_PATH = LOCAL_DATA_DIR / "sicurre.db"
POC_DATA_DB_PATH = LOCAL_DATA_DIR / "sicurre_datapatform.db"

POC_AUTH_DB_ASYNC_URL = f"sqlite+aiosqlite:///{POC_AUTH_DB_PATH.as_posix()}"
POC_DATA_DB_ASYNC_URL = f"sqlite+aiosqlite:///{POC_DATA_DB_PATH.as_posix()}"
POC_DATA_DB_SYNC_URL = f"sqlite:///{POC_DATA_DB_PATH.as_posix()}"

load_dotenv(ROOT_DIR / ".env", override=False)

DEFAULT_ADMIN_EMAIL = (
    os.environ.get("SICURRE_POC_ADMIN_EMAIL") or "admin.local@sicurre.test"
)
DEFAULT_ADMIN_PASSWORD = os.environ.get("SICURRE_POC_ADMIN_PASSWORD") or ""
DEFAULT_ADMIN_NAME = os.environ.get("SICURRE_POC_ADMIN_NAME", "Administrateur Sicurre")

DEFAULT_VIEWER_EMAIL = (
    os.environ.get("SICURRE_POC_VIEWER_EMAIL") or "viewer.local@sicurre.test"
)
DEFAULT_VIEWER_PASSWORD = os.environ.get("SICURRE_POC_VIEWER_PASSWORD") or ""
DEFAULT_VIEWER_NAME = os.environ.get("SICURRE_POC_VIEWER_NAME", "Utilisateur Démo")

POC_LOCAL_INFERENCE_API_URL = os.environ.get(
    "SICURRE_POC_INFERENCE_API_URL", "http://127.0.0.1:8000/v1/classify"
)
POC_LOCAL_INFERENCE_API_KEY = os.environ.get(
    "SICURRE_POC_INFERENCE_API_KEY", os.environ.get("INFERENCE_API_KEY", "")
)


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

    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(POC_AUTH_DB_PATH))
    try:
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
            CREATE TABLE IF NOT EXISTS poc_inference_event (
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

        event_columns = _table_columns(conn, "poc_inference_event")
        if "latency_ms" not in event_columns:
            conn.execute(
                "ALTER TABLE poc_inference_event ADD COLUMN latency_ms REAL NOT NULL DEFAULT 0"
            )
        if "used_llm" not in event_columns:
            conn.execute(
                "ALTER TABLE poc_inference_event ADD COLUMN used_llm INTEGER NOT NULL DEFAULT 0"
            )
        if "used_virustotal" not in event_columns:
            conn.execute(
                "ALTER TABLE poc_inference_event ADD COLUMN used_virustotal INTEGER NOT NULL DEFAULT 0"
            )
        if "inference_source" not in event_columns:
            conn.execute(
                "ALTER TABLE poc_inference_event ADD COLUMN inference_source TEXT NOT NULL DEFAULT 'api'"
            )
        for account in _seed_accounts():
            row = conn.execute(
                "SELECT id FROM poc_user WHERE email = ?",
                (account["email"],),
            ).fetchone()
            if row:
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
                    datetime.now(timezone.utc).isoformat(),
                    None,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def build_poc_command_env() -> dict[str, str]:
    env = dict(os.environ)
    env["SICURRE_DATABASE_URL"] = POC_AUTH_DB_ASYNC_URL
    env["SICURRE_DATA_PLATFORM_DATABASE_URL"] = POC_DATA_DB_ASYNC_URL
    env["INFERENCE_API_URL"] = POC_LOCAL_INFERENCE_API_URL
    if POC_LOCAL_INFERENCE_API_KEY:
        env["INFERENCE_API_KEY"] = POC_LOCAL_INFERENCE_API_KEY
    return env
