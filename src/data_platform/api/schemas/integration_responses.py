"""Typed response contracts for gateways and provider integrations."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from data_platform.api.schemas.app_responses import ApiResponse


class QuarantineCustodyResponse(ApiResponse):
    """Idempotent raw-MIME custody result."""

    status: Literal["stored"]
    idempotent: bool


class CloudflareDnsSyncResponse(ApiResponse):
    """Domain Shield values recomputed during provisioning."""

    zone_id: str
    dmarc_record: str | None = None
    dmarc_reporting_enabled: bool
    reputation_score: int = Field(ge=0, le=100)
    score_grade: str
    updated_at: str


class CloudflareWorkerUpdateResponse(ApiResponse):
    """Worker binding update performed during reprovisioning."""

    updated: bool
    scan_url: str
    worker_name: str


class CloudflareSetupResponse(ApiResponse):
    """Cloudflare provisioning or reprovisioning acknowledgement."""

    integration_id: str
    status: str
    zone_name: str
    destination_email: str
    dns_sync: CloudflareDnsSyncResponse | None = None
    worker_update: CloudflareWorkerUpdateResponse | None = None
    message: str


class CloudflareTeardownResponse(ApiResponse):
    """Removed Cloudflare integration."""

    status: Literal["removed"]
    zone_name: str
    # False only when Sicurre's DMARC reporting address could not be removed
    # from the zone, which an operator then has to finish by hand.
    dmarc_reporting_withdrawn: bool = True


class CloudflareDnsPlan(ApiResponse):
    """What connecting would change on the customer's zone.

    Derived from the same merge the write path uses, so what is shown before
    the button is what gets applied after it.
    """

    spf: Literal["add", "modify", "keep"]
    dmarc: Literal["add", "modify", "keep"]
    dkim_present: bool


class CloudflareTokenVerificationResponse(ApiResponse):
    """Cloudflare token and zone-access validation result."""

    valid: bool
    zone_id: str | None = None
    error: str | None = None
    plan: CloudflareDnsPlan | None = None


class CloudflareTokenStatusResponse(ApiResponse):
    """Presence of an encrypted workspace Cloudflare credential."""

    configured: bool


class ReportAddressResponse(ApiResponse):
    """Signed false-negative forwarding address."""

    address: str


class ReportedEmailSummary(ApiResponse):
    """One forwarded report, described without reproducing its content.

    Deliberately metadata only. The ingest pipeline anonymises the message and
    stores it in private R2 precisely so the forwarded content stops circulating;
    returning a body here would undo that. Date, size and status are enough for
    the person who forwarded it to see that it arrived.
    """

    id: str
    received_at: str
    size_bytes: int
    status: str


class ReportedEmailListResponse(ApiResponse):
    """Forwarded reports belonging to the authenticated workspace."""

    items: list[ReportedEmailSummary]


class ReportedEmailIngestResponse(ApiResponse):
    """Idempotent forwarded-message ingestion result."""

    status: Literal["accepted"]
    idempotent: bool


class PhishtankSnapshotResponse(ApiResponse):
    """Internal phishing URL snapshot consumed by Sicurre-ML."""

    urls: list[str]
    count: int = Field(ge=0)
    source: str
    generated_at: str


class HealthResponse(ApiResponse):
    """Process liveness and deployment environment.

    Deliberately says nothing about dependencies. Docker restarts the container
    when this fails, and restarting cannot reach an unreachable database.
    """

    status: Literal["ok"]
    environment: str


class ReadinessResponse(ApiResponse):
    """Whether the service can actually serve, dependencies included."""

    status: Literal["ready", "degraded"]
    environment: str
    database: Literal["reachable", "unreachable"]
    detail: str | None = None
    # How old the observation is. The keepalive refreshes it every 30s; when no
    # keepalive runs, the endpoint probes and this is near zero.
    observed_seconds_ago: float | None = None
