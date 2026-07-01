"""add workspace runtime tables and neutral inference event table

Revision ID: 20260621_0007
Revises: 20260521_0006
Create Date: 2026-06-21 13:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260621_0007"
down_revision = "20260521_0006"
branch_labels = None
depends_on = None


def _table_exists(connection: sa.Connection, table_name: str) -> bool:
    rows = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchall()
    return bool(rows)


def _column_names(connection: sa.Connection, table_name: str) -> set[str]:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def upgrade() -> None:
    connection = op.get_bind()

    op.execute("""
        CREATE TABLE IF NOT EXISTS app_workspace (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            owner_auth_user_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
    op.execute("""
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
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_app_workspace_membership_workspace_id ON app_workspace_membership(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_app_workspace_membership_email ON app_workspace_membership(email)"
    )

    if _table_exists(connection, "poc_inference_event") and not _table_exists(
        connection, "app_inference_event"
    ):
        op.execute("ALTER TABLE poc_inference_event RENAME TO app_inference_event")

    if not _table_exists(connection, "app_inference_event"):
        op.execute("""
            CREATE TABLE app_inference_event (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                user_email TEXT NOT NULL,
                workspace_id TEXT NULL,
                workspace_member_user_id TEXT NULL,
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
                stage_scores_json TEXT NOT NULL,
                stage_labels_json TEXT NOT NULL,
                stage_breakdown_json TEXT NOT NULL,
                expected_label TEXT NULL,
                latency_ms REAL NOT NULL DEFAULT 0,
                used_llm INTEGER NOT NULL DEFAULT 0,
                used_virustotal INTEGER NOT NULL DEFAULT 0,
                inference_source TEXT NOT NULL DEFAULT 'api',
                override_verdict TEXT NULL,
                override_by TEXT NULL,
                overridden_at TEXT NULL
            )
            """)

    event_columns = _column_names(connection, "app_inference_event")
    if "workspace_id" not in event_columns:
        op.execute("ALTER TABLE app_inference_event ADD COLUMN workspace_id TEXT NULL")
    if "workspace_member_user_id" not in event_columns:
        op.execute(
            "ALTER TABLE app_inference_event ADD COLUMN workspace_member_user_id TEXT NULL"
        )

    if not _table_exists(connection, "cloudflare_integration"):
        op.execute("""
            CREATE TABLE cloudflare_integration (
                id TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                workspace_id TEXT NULL,
                workspace_member_user_id TEXT NULL,
                zone_id TEXT NOT NULL,
                zone_name TEXT NOT NULL,
                account_id TEXT NOT NULL,
                worker_name TEXT NOT NULL,
                rule_id TEXT NOT NULL DEFAULT 'unknown',
                destination_email TEXT NOT NULL,
                api_token TEXT NULL,
                shared_secret_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_verification',
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

    integration_columns = _column_names(connection, "cloudflare_integration")
    if "workspace_id" not in integration_columns:
        op.execute(
            "ALTER TABLE cloudflare_integration ADD COLUMN workspace_id TEXT NULL"
        )
    if "workspace_member_user_id" not in integration_columns:
        op.execute(
            "ALTER TABLE cloudflare_integration ADD COLUMN workspace_member_user_id TEXT NULL"
        )


def downgrade() -> None:
    connection = op.get_bind()

    if _table_exists(connection, "app_inference_event") and not _table_exists(
        connection, "poc_inference_event"
    ):
        op.execute("ALTER TABLE app_inference_event RENAME TO poc_inference_event")

    op.execute("DROP INDEX IF EXISTS ix_app_workspace_membership_email")
    op.execute("DROP INDEX IF EXISTS ix_app_workspace_membership_workspace_id")
    op.execute("DROP TABLE IF EXISTS app_workspace_membership")
    op.execute("DROP TABLE IF EXISTS app_workspace")
