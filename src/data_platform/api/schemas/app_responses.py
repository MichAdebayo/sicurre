"""Typed response contracts for the Sicurre application API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    """Reject undeclared response fields so documentation drift fails at runtime."""

    model_config = ConfigDict(extra="forbid")


class AuthSessionResponse(ApiResponse):
    """Authenticated workspace and onboarding state."""

    id: str
    email: str
    display_name: str
    role: str
    workspace_id: str
    workspace_name: str
    is_platform_admin: bool
    has_cloudflare_integration: bool
    threat_count: int = Field(ge=0)
    onboarding_required: bool
    sla_latency_ms: int = Field(ge=0)


class KpiResponse(ApiResponse):
    """Workspace and dataset counters displayed by the dashboard."""

    raw_records_count: int = Field(ge=0)
    normalized_messages_count: int = Field(ge=0)
    dataset_items_count: int = Field(ge=0)
    threats_phishing_count: int = Field(ge=0)
    threats_spam_count: int = Field(ge=0)
    threats_legitimate_count: int = Field(ge=0)


class ThreatLogResponse(ApiResponse):
    """Privacy-preserving representation of one classified message."""

    id: str
    message_id: str | None = None
    privacy_reference: str
    content_redacted: bool
    subject: str | None = None
    sender: str | None = None
    body_preview: str | None = None
    verdict: Literal["phishing", "spam", "legitimate", "quarantine"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    received_at: str | None = None
    status: Literal["active", "trashed", "restored"]
    latency_ms: float | None = Field(default=None, ge=0)
    explanation: str | None = None


class ThreatPageResponse(ApiResponse):
    """One bounded page of classified messages."""

    items: list[ThreatLogResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    pages: int = Field(ge=1)


class ThreatVisibilityResponse(ApiResponse):
    """Result of hiding or restoring workspace events."""

    updated: int = Field(ge=0)
    hidden: bool


class FeedbackResponse(ApiResponse):
    """Persisted classification correction."""

    id: str
    event_id: str | None = None
    feedback_type: str
    original_verdict: str | None = None
    corrected_verdict: str
    created_at: str


class SupportResponse(ApiResponse):
    """Accepted support request."""

    id: str
    status: Literal["open"]
    created_at: str


class RuntimeComponentResponse(ApiResponse):
    """Health result for one deployed component."""

    component: str
    status: Literal["ok", "degraded", "down", "unknown"]
    message: str
    detail: str | None = None
    checked_url: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)


class AdminRuntimeHealthResponse(ApiResponse):
    """Aggregated platform health visible to administrators."""

    status: Literal["ok", "degraded", "down", "unknown"]
    checked_at: str
    public_api_host: str | None = None
    inference_api_url: str | None = None
    expected_worker_scan_url: str | None = None
    components: list[RuntimeComponentResponse]


class AdminSummaryResponse(ApiResponse):
    """Platform-wide bounded counters."""

    workspaces_count: int = Field(ge=0)
    members_count: int = Field(ge=0)
    threat_events_count: int = Field(ge=0)
    feedback_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    reported_email_count: int = Field(ge=0)
    quarantine_held_count: int = Field(ge=0)
    cloudflare_integrations_count: int = Field(ge=0)
    cloudflare_active_count: int = Field(ge=0)
    support_open_count: int = Field(ge=0)


class VerdictCountResponse(ApiResponse):
    """Count grouped by classifier verdict."""

    verdict: str
    count: int = Field(ge=0)


class FeedbackCountResponse(ApiResponse):
    """Count grouped by feedback type."""

    feedback_type: str
    count: int = Field(ge=0)


class AdminDomainResponse(ApiResponse):
    """Bounded Cloudflare domain inventory row."""

    zone_name: str | None = None
    status: str | None = None
    user_email: str | None = None
    updated_at: str | None = None


class AdminFeedbackResponse(ApiResponse):
    """Recent feedback audit row."""

    id: str
    workspace_id: str
    feedback_type: str
    original_verdict: str | None = None
    corrected_verdict: str
    created_at: str
    reporter_email: str | None = None


class AdminQuarantineResponse(ApiResponse):
    """Recent quarantine audit row."""

    id: str
    workspace_id: str
    safety_verdict: str
    composite_score: float
    status: str
    created_at: str
    expires_at: str


class AdminSupportResponse(ApiResponse):
    """Recent support request audit row."""

    id: str
    workspace_id: str
    requester_email: str
    category: str
    status: str
    created_at: str


class AdminOverviewResponse(ApiResponse):
    """Bounded operational overview for platform administrators."""

    summary: AdminSummaryResponse
    verdicts: list[VerdictCountResponse]
    feedback_by_type: list[FeedbackCountResponse]
    cloudflare_domains: list[AdminDomainResponse]
    recent_feedback: list[AdminFeedbackResponse]
    recent_quarantine: list[AdminQuarantineResponse]
    recent_support: list[AdminSupportResponse]


class AdminDomainPageResponse(ApiResponse):
    """Searchable page of connected customer domains."""

    items: list[AdminDomainResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    pages: int = Field(ge=1)


class OperationalExerciseResponse(ApiResponse):
    """One controlled monitoring exercise."""

    id: str
    exercise_type: Literal["api_unavailable", "high_latency", "elevated_5xx"]
    initiated_by: str
    started_at: str
    expires_at: str
    status: Literal["active", "recovered"] | None = None
    recovered_at: str | None = None


class OperationalExerciseStateResponse(ApiResponse):
    """Current and recent controlled monitoring exercises."""

    enabled: bool
    active: OperationalExerciseResponse | None
    recent: list[OperationalExerciseResponse]
    supported_types: list[Literal["api_unavailable", "high_latency", "elevated_5xx"]]


class DatasetSummaryResponse(ApiResponse):
    """Published or draft dataset visible to administrators."""

    id: str
    version_tag: str
    item_count: int = Field(ge=0)
    status: str
    published_at: str | None = None


class PipelineRunResponse(ApiResponse):
    """Asynchronous source-ingestion trigger acknowledgement."""

    run_id: str


class QuarantineItemResponse(ApiResponse):
    """Held message metadata and bounded content preview."""

    id: str
    message_id: str
    sender: str
    subject: str
    body_text: str
    safety_verdict: str
    composite_score: float
    status: str
    created_at: str
    expires_at: str


class QuarantineReleaseResponse(ApiResponse):
    """Idempotent quarantine restoration result."""

    status: Literal["released"]
    forwarded_to: str
    delivery_message_id: str | None = None
    queued: bool | None = None
    idempotent: bool


class QuarantineWhitelistResponse(QuarantineReleaseResponse):
    """Restoration result with the tenant whitelist rule created."""

    whitelisted_pattern: str


class StatusResponse(ApiResponse):
    """Stable acknowledgement for a completed command."""

    status: str


class AlertPreferenceResponse(ApiResponse):
    """Workspace notification preferences."""

    notify_phishing: bool
    notify_spam: bool
    quiet_hours_enabled: bool
    quiet_hours_start: str
    quiet_hours_end: str
    timezone: str


class SecurityRuleResponse(ApiResponse):
    """Workspace sender or domain rule."""

    id: str
    rule_type: Literal["whitelist", "blocklist"]
    pattern: str
    created_at: str | None = None


class AlertHistoryResponse(ApiResponse):
    """One customer-visible notification."""

    id: str
    title: str
    message: str
    created_at: str


class CloudflareIntegrationResponse(ApiResponse):
    """Sanitized Cloudflare integration state; credentials are never returned."""

    status: str
    id: str | None = None
    user_email: str | None = None
    zone_name: str | None = None
    destination_email: str | None = None
    worker_name: str | None = None
    token_configured: bool | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DnsRecordStatusResponse(ApiResponse):
    """Validation state for an email authentication record."""

    valid: bool
    record: str | None = None
    error: str | None = None


class DmarcStatusResponse(DnsRecordStatusResponse):
    """DMARC validation and reporting state."""

    policy: str
    reporting_enabled: bool = False


class SslStatusResponse(ApiResponse):
    """Public certificate state."""

    valid: bool
    days_remaining: int
    auto_renew: bool
    error: str | None = None


class BlacklistStatusResponse(ApiResponse):
    """Consolidated reputation-provider result."""

    listed: bool
    matched: list[str]
    error: str | None = None


class DomainShieldResponse(ApiResponse):
    """Current DNS, TLS, and reputation posture for one connected domain."""

    spf: DnsRecordStatusResponse
    dkim: DnsRecordStatusResponse
    dmarc: DmarcStatusResponse
    ssl: SslStatusResponse
    reputation_score: int = Field(ge=0, le=100)
    score_grade: str
    blacklists: BlacklistStatusResponse
    updated_at: str | None = None


class DmarcSourceResponse(ApiResponse):
    """Aggregate DMARC result grouped by sending source."""

    source_ip: str
    message_count: int = Field(ge=0)
    disposition: str | None = None
    dkim_result: str | None = None
    spf_result: str | None = None


class DmarcSummaryResponse(ApiResponse):
    """Tenant-scoped aggregate DMARC report summary."""

    domain: str
    total_messages: int = Field(ge=0)
    aligned_messages: int = Field(ge=0)
    failed_messages: int = Field(ge=0)
    report_count: int = Field(ge=0)
    last_report_at: str | None = None
    top_sources: list[DmarcSourceResponse]


class DmarcImportResponse(ApiResponse):
    """Idempotent DMARC import result."""

    status: Literal["imported", "already_imported"]
    record_count: int = Field(ge=0)
