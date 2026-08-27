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


class CloudflareTokenVerificationResponse(ApiResponse):
    """Cloudflare token and zone-access validation result."""

    valid: bool
    zone_id: str | None = None
    error: str | None = None


class CloudflareTokenStatusResponse(ApiResponse):
    """Presence of an encrypted workspace Cloudflare credential."""

    configured: bool


class ReportAddressResponse(ApiResponse):
    """Signed false-negative forwarding address."""

    address: str


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
    """Process liveness and deployment environment."""

    status: Literal["ok"]
    environment: str
