"""Scope application events and notification policy to a connected domain.

Revision ID: 20260830_app_0008
Revises: 20260806_0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from db.models.app_runtime import app_alert_read

revision = "20260830_app_0008"
down_revision = "20260806_0007"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def _backfill_unambiguous_domains(table: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET domain = (
                SELECT MIN(zone_name)
                FROM cloudflare_integration
                WHERE cloudflare_integration.workspace_id = {table}.workspace_id
            )
            WHERE domain IS NULL
              AND 1 = (
                SELECT COUNT(DISTINCT lower(zone_name))
                FROM cloudflare_integration
                WHERE cloudflare_integration.workspace_id = {table}.workspace_id
              )
            """
        )
    )


def _create_index(name: str, table: str) -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, ["workspace_id", "domain"])


def upgrade() -> None:
    """Add trusted domain attribution and per-domain notification state."""
    for table in (
        "app_inference_event",
        "app_quarantine_item",
        "app_alert_history",
        "app_security_rule",
    ):
        _add_column(table, sa.Column("domain", sa.Text(), nullable=True))
        _backfill_unambiguous_domains(table)

    _add_column(
        "app_alert_history",
        sa.Column("event_type", sa.Text(), nullable=False, server_default="system"),
    )
    _add_column("app_alert_history", sa.Column("action_page", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE app_alert_history SET event_type = 'phishing_quarantine', "
            "action_page = 'quarantine' WHERE title = 'Email mis en quarantaine'"
        )
    )

    _create_index("ix_app_inference_event_workspace_domain", "app_inference_event")
    _create_index("ix_app_quarantine_item_workspace_domain", "app_quarantine_item")
    _create_index("ix_app_alert_history_workspace_domain", "app_alert_history")
    _create_index("ix_app_security_rule_workspace_domain", "app_security_rule")

    quarantine_uniques = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_unique_constraints("app_quarantine_item")
    }
    if "uq_app_quarantine_workspace_message" in quarantine_uniques:
        with op.batch_alter_table("app_quarantine_item") as batch:
            batch.drop_constraint("uq_app_quarantine_workspace_message", type_="unique")
    quarantine_indexes = {
        item["name"] for item in sa.inspect(op.get_bind()).get_indexes("app_quarantine_item")
    }
    if (
        "uq_app_quarantine_workspace_domain_message" not in quarantine_indexes
        and "uq_app_quarantine_workspace_domain_message" not in quarantine_uniques
    ):
        op.create_index(
            "uq_app_quarantine_workspace_domain_message",
            "app_quarantine_item",
            ["workspace_id", "domain", "message_id"],
            unique=True,
        )

    preference_columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns("app_alert_preference")
    }
    if "domain" not in preference_columns:
        op.create_table(
            "app_alert_preference_v2",
            sa.Column("workspace_id", sa.Text(), nullable=False),
            sa.Column("domain", sa.Text(), nullable=False),
            sa.Column("email_enabled", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("notify_phishing", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("notify_domain_shield", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("quiet_hours_enabled", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("quiet_hours_start", sa.Text(), nullable=False, server_default="22:00"),
            sa.Column("quiet_hours_end", sa.Text(), nullable=False, server_default="07:00"),
            sa.Column("timezone", sa.Text(), nullable=False, server_default="Europe/Paris"),
            sa.PrimaryKeyConstraint("workspace_id", "domain"),
        )
        op.execute(
            sa.text(
                """
                INSERT INTO app_alert_preference_v2 (
                    workspace_id, domain, email_enabled, notify_phishing,
                    notify_domain_shield, quiet_hours_enabled, quiet_hours_start,
                    quiet_hours_end, timezone
                )
                SELECT DISTINCT p.workspace_id, lower(i.zone_name), 1,
                    p.notify_phishing, 1, p.quiet_hours_enabled,
                    p.quiet_hours_start, p.quiet_hours_end, p.timezone
                FROM app_alert_preference p
                JOIN cloudflare_integration i ON i.workspace_id = p.workspace_id
                """
            )
        )
        op.drop_table("app_alert_preference")
        op.rename_table("app_alert_preference_v2", "app_alert_preference")
    app_alert_read.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Restore the former workspace-wide preference shape."""
    app_alert_read.drop(bind=op.get_bind(), checkfirst=True)
    op.create_table(
        "app_alert_preference_v1",
        sa.Column("workspace_id", sa.Text(), primary_key=True),
        sa.Column("notify_phishing", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notify_spam", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quiet_hours_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quiet_hours_start", sa.Text(), nullable=False, server_default="22:00"),
        sa.Column("quiet_hours_end", sa.Text(), nullable=False, server_default="07:00"),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="Europe/Paris"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO app_alert_preference_v1
            SELECT workspace_id, MAX(email_enabled * notify_phishing), 0,
                MAX(quiet_hours_enabled), MIN(quiet_hours_start),
                MIN(quiet_hours_end), MIN(timezone)
            FROM app_alert_preference GROUP BY workspace_id
            """
        )
    )
    op.drop_table("app_alert_preference")
    op.rename_table("app_alert_preference_v1", "app_alert_preference")

    quarantine_indexes = {
        item["name"] for item in sa.inspect(op.get_bind()).get_indexes("app_quarantine_item")
    }
    if "uq_app_quarantine_workspace_domain_message" in quarantine_indexes:
        op.drop_index(
            "uq_app_quarantine_workspace_domain_message",
            table_name="app_quarantine_item",
        )
    quarantine_uniques = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_unique_constraints("app_quarantine_item")
    }
    if "uq_app_quarantine_workspace_domain_message" in quarantine_uniques:
        with op.batch_alter_table("app_quarantine_item") as batch:
            batch.drop_constraint(
                "uq_app_quarantine_workspace_domain_message",
                type_="unique",
            )
        quarantine_uniques.remove("uq_app_quarantine_workspace_domain_message")
    if "uq_app_quarantine_workspace_message" not in quarantine_uniques:
        with op.batch_alter_table("app_quarantine_item") as batch:
            batch.create_unique_constraint(
                "uq_app_quarantine_workspace_message",
                ["workspace_id", "message_id"],
            )

    for index_name, table in (
        ("ix_app_inference_event_workspace_domain", "app_inference_event"),
        ("ix_app_quarantine_item_workspace_domain", "app_quarantine_item"),
        ("ix_app_alert_history_workspace_domain", "app_alert_history"),
        ("ix_app_security_rule_workspace_domain", "app_security_rule"),
    ):
        op.drop_index(index_name, table_name=table)
    with op.batch_alter_table("app_alert_history") as batch:
        batch.drop_column("action_page")
        batch.drop_column("event_type")
        batch.drop_column("domain")
    with op.batch_alter_table("app_quarantine_item") as batch:
        batch.drop_column("domain")
    with op.batch_alter_table("app_inference_event") as batch:
        batch.drop_column("domain")
    with op.batch_alter_table("app_security_rule") as batch:
        batch.drop_column("domain")
