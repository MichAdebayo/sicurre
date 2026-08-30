"""Cross-dialect application runtime tables owned by Sicurre."""

from __future__ import annotations

import sqlalchemy as sa

from core.database import Base

APP_TABLE_NAMES = (
    "app_workspace",
    "app_workspace_membership",
    "cloudflare_integration",
    "app_inference_event",
    "app_cloudflare_config",
    "app_security_rule",
    "app_alert_preference",
    "app_alert_history",
    "app_alert_read",
    "app_quarantine_item",
    "app_domain_shield_status",
    "app_domain_shield_history",
    "app_dmarc_report_summary",
    "app_feedback",
    "app_reported_email",
    "app_support_request",
    "app_operational_exercise",
)


def _text_column(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column:
    kwargs: dict[str, object] = {"nullable": nullable}
    if default is not None:
        kwargs["server_default"] = sa.text(f"'{default}'")
    return sa.Column(name, sa.Text(), **kwargs)


app_workspace = sa.Table(
    "app_workspace",
    Base.metadata,
    _text_column("id", nullable=False),
    _text_column("name", nullable=False),
    _text_column("slug", nullable=False),
    _text_column("owner_auth_user_id", nullable=False),
    _text_column("created_at", nullable=False),
    _text_column("updated_at", nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("slug"),
    sa.UniqueConstraint("owner_auth_user_id"),
)

app_workspace_membership = sa.Table(
    "app_workspace_membership",
    Base.metadata,
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("auth_user_id", nullable=False),
    _text_column("email", nullable=False),
    _text_column("display_name", nullable=False),
    _text_column("role", nullable=False),
    _text_column("created_at", nullable=False),
    _text_column("updated_at", nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.ForeignKeyConstraint(["workspace_id"], ["app_workspace.id"], ondelete="CASCADE"),
    sa.UniqueConstraint("auth_user_id"),
    sa.UniqueConstraint("workspace_id", "auth_user_id"),
    sa.Index("ix_app_workspace_membership_workspace_id", "workspace_id"),
    sa.Index("ix_app_workspace_membership_email", "email"),
)

cloudflare_integration = sa.Table(
    "cloudflare_integration",
    Base.metadata,
    _text_column("id", nullable=False),
    _text_column("user_email", nullable=False),
    _text_column("workspace_id", nullable=True),
    _text_column("workspace_member_user_id", nullable=True),
    _text_column("zone_id", nullable=False),
    _text_column("zone_name", nullable=False),
    _text_column("account_id", nullable=False),
    _text_column("worker_name", nullable=False),
    _text_column("rule_id", nullable=False, default="unknown"),
    _text_column("destination_email", nullable=False),
    _text_column("api_token", nullable=True),
    _text_column("shared_secret_hash", nullable=False),
    _text_column("status", nullable=False, default="pending_verification"),
    _text_column("error_message", nullable=True),
    _text_column("created_at", nullable=False),
    _text_column("updated_at", nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.Index("ix_cloudflare_integration_workspace_id", "workspace_id"),
)

app_inference_event = sa.Table(
    "app_inference_event",
    Base.metadata,
    _text_column("id", nullable=False),
    _text_column("created_at", nullable=False),
    _text_column("user_email", nullable=False),
    _text_column("workspace_id", nullable=True),
    _text_column("workspace_member_user_id", nullable=True),
    _text_column("domain", nullable=True),
    _text_column("context", nullable=False),
    _text_column("subject", nullable=False),
    _text_column("sender", nullable=False),
    _text_column("snippet", nullable=False),
    _text_column("safety_verdict", nullable=False),
    _text_column("label_verdict", nullable=False),
    sa.Column("composite_score", sa.Float(), nullable=False),
    sa.Column("is_phishing", sa.Integer(), nullable=False),
    sa.Column("delivered_in_smail", sa.Integer(), nullable=False),
    _text_column("llm_provider", nullable=False),
    _text_column("explanation", nullable=False),
    sa.Column("latency_ms", sa.Float(), nullable=False, server_default=sa.text("0")),
    sa.Column("used_llm", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.Column("used_virustotal", sa.Integer(), nullable=False, server_default=sa.text("0")),
    _text_column("inference_source", nullable=False, default="api"),
    _text_column("stage_scores_json", nullable=False, default="{}"),
    _text_column("stage_labels_json", nullable=False, default="{}"),
    _text_column("stage_breakdown_json", nullable=False, default="{}"),
    _text_column("expected_label", nullable=True),
    _text_column("override_verdict", nullable=True),
    _text_column("override_by", nullable=True),
    _text_column("overridden_at", nullable=True),
    sa.Column("is_deleted", sa.Integer(), nullable=False, server_default=sa.text("0")),
    sa.PrimaryKeyConstraint("id"),
    sa.Index("ix_app_inference_event_workspace_id", "workspace_id"),
    sa.Index("ix_app_inference_event_workspace_domain", "workspace_id", "domain"),
)


def _workspace_table(
    name: str, *columns: sa.Column, constraints: tuple[sa.SchemaItem, ...] = ()
) -> sa.Table:
    return sa.Table(name, Base.metadata, *columns, *constraints)


app_cloudflare_config = _workspace_table(
    "app_cloudflare_config",
    _text_column("workspace_id", nullable=False),
    _text_column("api_token", nullable=False),
    _text_column("created_at", nullable=False),
    _text_column("updated_at", nullable=False),
    constraints=(sa.PrimaryKeyConstraint("workspace_id"),),
)

app_security_rule = _workspace_table(
    "app_security_rule",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("domain", nullable=False),
    _text_column("rule_type", nullable=False),
    _text_column("pattern", nullable=False),
    _text_column("created_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_app_security_rule_workspace_id", "workspace_id"),
        sa.Index("ix_app_security_rule_workspace_domain", "workspace_id", "domain"),
    ),
)

app_alert_preference = _workspace_table(
    "app_alert_preference",
    _text_column("workspace_id", nullable=False),
    _text_column("domain", nullable=False),
    sa.Column("email_enabled", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column("notify_phishing", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column("notify_domain_shield", sa.Integer(), nullable=False, server_default=sa.text("1")),
    sa.Column("quiet_hours_enabled", sa.Integer(), nullable=False, server_default=sa.text("0")),
    _text_column("quiet_hours_start", nullable=False, default="22:00"),
    _text_column("quiet_hours_end", nullable=False, default="07:00"),
    _text_column("timezone", nullable=False, default="Europe/Paris"),
    constraints=(sa.PrimaryKeyConstraint("workspace_id", "domain"),),
)

app_alert_history = _workspace_table(
    "app_alert_history",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("domain", nullable=True),
    _text_column("event_type", nullable=False, default="system"),
    _text_column("action_page", nullable=True),
    _text_column("title", nullable=False),
    _text_column("message", nullable=False),
    sa.Column("is_dismissed", sa.Integer(), nullable=False, server_default=sa.text("0")),
    _text_column("created_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_app_alert_history_workspace_id", "workspace_id"),
        sa.Index("ix_app_alert_history_workspace_domain", "workspace_id", "domain"),
    ),
)

app_alert_read = _workspace_table(
    "app_alert_read",
    _text_column("workspace_id", nullable=False),
    _text_column("domain", nullable=False),
    _text_column("auth_user_id", nullable=False),
    _text_column("alert_id", nullable=False),
    _text_column("read_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("auth_user_id", "alert_id"),
        sa.Index("ix_app_alert_read_workspace_domain", "workspace_id", "domain"),
    ),
)

app_operational_exercise = _workspace_table(
    "app_operational_exercise",
    _text_column("id", nullable=False),
    _text_column("exercise_type", nullable=False),
    _text_column("status", nullable=False),
    _text_column("initiated_by", nullable=False),
    _text_column("started_at", nullable=False),
    _text_column("expires_at", nullable=False),
    _text_column("recovered_at", nullable=True),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_app_operational_exercise_started_at", "started_at"),
    ),
)

app_quarantine_item = _workspace_table(
    "app_quarantine_item",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("domain", nullable=True),
    _text_column("message_id", nullable=False),
    _text_column("sender", nullable=False),
    _text_column("subject", nullable=False),
    _text_column("body_text", nullable=False),
    _text_column("raw_storage_uri", nullable=True),
    _text_column("raw_content_hash", nullable=True),
    sa.Column("raw_size_bytes", sa.Integer(), nullable=True),
    _text_column("safety_verdict", nullable=False),
    sa.Column("composite_score", sa.Float(), nullable=False),
    _text_column("status", nullable=False, default="held"),
    _text_column("created_at", nullable=False),
    _text_column("expires_at", nullable=False),
    _text_column("delivery_message_id", nullable=True),
    _text_column("delivered_at", nullable=True),
    _text_column("last_delivery_error", nullable=True),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "domain",
            "message_id",
            name="uq_app_quarantine_workspace_domain_message",
        ),
        sa.Index("ix_app_quarantine_item_workspace_id", "workspace_id"),
        sa.Index("ix_app_quarantine_item_workspace_domain", "workspace_id", "domain"),
    ),
)

app_domain_shield_status = _workspace_table(
    "app_domain_shield_status",
    _text_column("domain", nullable=False),
    _text_column("workspace_id", nullable=False),
    sa.Column("spf_valid", sa.Integer(), nullable=False),
    _text_column("spf_record", nullable=True),
    sa.Column("dkim_valid", sa.Integer(), nullable=False),
    _text_column("dkim_record", nullable=True),
    sa.Column("dmarc_valid", sa.Integer(), nullable=False),
    _text_column("dmarc_record", nullable=True),
    _text_column("dmarc_policy", nullable=True),
    sa.Column("ssl_valid", sa.Integer(), nullable=False),
    sa.Column("ssl_days_remaining", sa.Integer(), nullable=False),
    sa.Column("reputation_score", sa.Integer(), nullable=False),
    _text_column("score_grade", nullable=False),
    _text_column("updated_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("domain"),
        sa.Index("ix_app_domain_shield_status_workspace_id", "workspace_id"),
    ),
)

app_domain_shield_history = _workspace_table(
    "app_domain_shield_history",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("domain", nullable=False),
    sa.Column("reputation_score", sa.Integer(), nullable=False),
    _text_column("score_grade", nullable=False),
    sa.Column("spf_valid", sa.Integer(), nullable=False),
    sa.Column("dkim_valid", sa.Integer(), nullable=False),
    sa.Column("dmarc_valid", sa.Integer(), nullable=False),
    sa.Column("ssl_valid", sa.Integer(), nullable=False),
    _text_column("start_date", nullable=False),
    _text_column("end_date", nullable=True),
    sa.Column("is_current", sa.Integer(), nullable=False, server_default=sa.text("1")),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_app_domain_shield_history_domain", "domain"),
    ),
)

app_dmarc_report_summary = _workspace_table(
    "app_dmarc_report_summary",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("domain", nullable=False),
    _text_column("report_org", nullable=True),
    _text_column("report_id", nullable=True),
    _text_column("period_begin", nullable=True),
    _text_column("period_end", nullable=True),
    _text_column("source_ip", nullable=False),
    sa.Column("message_count", sa.Integer(), nullable=False),
    _text_column("disposition", nullable=True),
    _text_column("dkim_result", nullable=True),
    _text_column("spf_result", nullable=True),
    _text_column("header_from", nullable=True),
    _text_column("report_fingerprint", nullable=True),
    _text_column("created_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_app_dmarc_report_summary_workspace_domain", "workspace_id", "domain"),
        sa.UniqueConstraint(
            "workspace_id",
            "report_fingerprint",
            name="uq_app_dmarc_report_workspace_fingerprint",
        ),
    ),
)

app_feedback = _workspace_table(
    "app_feedback",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("workspace_member_user_id", nullable=False),
    _text_column("event_id", nullable=True),
    _text_column("feedback_type", nullable=False),
    _text_column("original_verdict", nullable=True),
    _text_column("corrected_verdict", nullable=False),
    _text_column("reporter_note", nullable=True),
    _text_column("created_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "event_id", "feedback_type"),
        sa.Index("ix_app_feedback_workspace_id", "workspace_id"),
        sa.Index("ix_app_feedback_event_id", "event_id"),
    ),
)

app_reported_email = _workspace_table(
    "app_reported_email",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("workspace_member_user_id", nullable=False),
    _text_column("storage_uri", nullable=False),
    _text_column("content_hash", nullable=False),
    sa.Column("size_bytes", sa.Integer(), nullable=False),
    _text_column("status", nullable=False, default="received"),
    _text_column("received_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "content_hash",
            name="uq_app_reported_email_workspace_hash",
        ),
        sa.Index("ix_app_reported_email_workspace_id", "workspace_id"),
    ),
)

app_support_request = _workspace_table(
    "app_support_request",
    _text_column("id", nullable=False),
    _text_column("workspace_id", nullable=False),
    _text_column("workspace_member_user_id", nullable=False),
    _text_column("requester_name", nullable=False),
    _text_column("requester_email", nullable=False),
    _text_column("category", nullable=False),
    _text_column("message", nullable=False),
    _text_column("status", nullable=False, default="open"),
    _text_column("created_at", nullable=False),
    _text_column("updated_at", nullable=False),
    constraints=(
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_app_support_request_workspace_id", "workspace_id"),
        sa.Index("ix_app_support_request_status", "status"),
    ),
)
