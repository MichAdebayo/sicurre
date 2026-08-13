"""Typed runtime configuration for Sicurre services and data jobs."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"


_DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{_DB_PATH.as_posix()}"


class Settings(BaseSettings):
    """Resolve validated settings from Sicurre environment files."""

    app_name: str = "Sicurre API"
    environment: str = "dev"
    database_url: str = _DEFAULT_DB_URL
    data_platform_database_url: str = _DEFAULT_DB_URL
    app_neon_database_url: str | None = None
    database_echo: bool = False
    database_historical_cron_total_count: int = 0
    database_historical_cron_max_total_count: int = 1000
    gcp_project: str = "sicurre"
    gcp_region: str = "europe-west1"
    bigquery_dataset_id: str = Field(
        default="sicurre_dataset",
        validation_alias="DATASET_ID",
    )
    auth_enabled: bool = True
    auth_allow_dev_tokens: bool | None = None
    auth_dev_bearer_tokens: str = "dev-token,dev-rate-limit"
    better_auth_base_url: str | None = "http://127.0.0.1:3005"
    better_auth_session_path: str = "/api/auth/get-session"
    better_auth_timeout_seconds: float = 12.0
    better_auth_cookie_name: str = "better-auth.session_token"
    better_auth_schema: str = "auth"
    platform_admin_emails: str = ""
    secret_encryption_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SICURRE_SECRET_ENCRYPTION_KEY",
            "secret_encryption_key",
        ),
        repr=False,
        description="URL-safe base64 encoding of the 32-byte application secret key.",
    )
    raw_snapshot_storage_backend: str = "local"
    raw_snapshot_local_dir: Path = ROOT_DIR / "data" / "raw" / "api"
    raw_snapshot_prefix: str = "raw-snapshots"
    raw_snapshot_r2_bucket_name: str | None = None
    raw_snapshot_r2_endpoint_url: str | None = None
    raw_snapshot_r2_access_key_id: str | None = None
    raw_snapshot_r2_secret_access_key: str | None = None
    raw_snapshot_r2_region: str = "auto"
    quarantine_storage_backend: str = "local"
    quarantine_local_dir: Path = ROOT_DIR / "data" / "local" / "quarantine"
    quarantine_r2_bucket_name: str | None = None
    quarantine_r2_prefix: str = "quarantine"
    quarantine_retention_days: int = Field(default=14, ge=1, le=90)
    quarantine_max_message_bytes: int = 5 * 1024 * 1024
    reported_email_address: str = "report@sicurre.com"
    reported_email_alias_secret: str | None = Field(default=None, repr=False)
    reported_email_ingest_key: str | None = Field(default=None, repr=False)
    reported_email_storage_backend: str = "local"
    reported_email_local_dir: Path = ROOT_DIR / "data" / "local" / "reported-email"
    reported_email_r2_bucket_name: str | None = None
    reported_email_r2_endpoint_url: str | None = None
    reported_email_r2_access_key_id: str | None = None
    reported_email_r2_secret_access_key: str | None = Field(default=None, repr=False)
    reported_email_r2_region: str = "auto"
    reported_email_r2_prefix: str = "reported-email"
    reported_email_max_message_bytes: int = 5 * 1024 * 1024
    phishtank_api_key: str | None = None
    phishtank_user_agent: str = "phishtank/sicurre-research"
    spamhaus_dqs_key: str | None = Field(
        default=None,
        validation_alias="SPAMHAUSE_DQS_API_KEY",
        description="Spamhaus DQS API key for authenticated DNSBL queries.",
    )
    phishtank_snapshot_storage_backend: str | None = None
    phishtank_snapshot_local_dir: Path = ROOT_DIR / "data" / "raw" / "api" / "phishtank"
    phishtank_snapshot_prefix: str = "phishtank"
    certfr_snapshot_storage_backend: str | None = None
    certfr_snapshot_prefix: str = "cert-fr"
    sekoia_snapshot_storage_backend: str | None = None
    sekoia_snapshot_prefix: str = "sekoia-community-ioc"
    sap_labs_snapshot_storage_backend: str | None = None
    common_crawl_snapshot_storage_backend: str | None = None
    database_historical_snapshot_storage_backend: str | None = None
    database_historical_snapshot_prefix: str = "db_historical"
    training_dataset_snapshot_storage_backend: str | None = "prod"
    training_dataset_snapshot_prefix: str = "training_dataset"
    cc_cron_duration_mode: str = Field(
        default="short",
        description="'short' = 30 min, 'standard' = 8 hours max runtime for CC cron.",
    )
    cc_cron_lookback_indices: int = Field(
        default=18,
        description="How many recent Common Crawl indexes the cron scans for missed work.",
    )
    cc_cron_index_max_attempts: int = Field(
        default=3,
        description="Per-index retry attempts before recording a Common Crawl failure.",
    )
    cc_cron_index_retry_backoff_seconds: int = Field(
        default=60,
        description="Initial retry backoff for Common Crawl index-level failures.",
    )
    cc_max_warc_downloads: int = Field(
        default=50_000,
        validation_alias="CC_MAX_WARC_DOWNLOADS",
        ge=1,
        description="Maximum WARC byte-range downloads attempted for one CC index.",
    )
    cc_max_results_per_query: int = Field(
        default=5_000,
        validation_alias="CC_MAX_RESULTS_PER_QUERY",
        ge=1,
        description="Maximum Common Crawl index hits collected for one query.",
    )
    cc_async_concurrency: int = Field(
        default=40,
        validation_alias="CC_ASYNC_CONCURRENCY",
        ge=1,
        description="Concurrent HTTP requests used by the incremental CC extractor.",
    )
    cc_min_text_length: int = Field(
        default=100,
        validation_alias="CC_MIN_TEXT_LENGTH",
        ge=1,
        description="Minimum extracted text length retained from a CC WARC response.",
    )
    cc_max_text_length: int = Field(
        default=10_000,
        validation_alias="CC_MAX_TEXT_LENGTH",
        ge=1,
        description="Maximum extracted text length retained from a CC WARC response.",
    )
    cc_request_timeout: int = Field(
        default=45,
        validation_alias="CC_REQUEST_TIMEOUT",
        ge=1,
        description="HTTP timeout in seconds for Common Crawl index and WARC requests.",
    )
    cc_warc_max_retries: int = Field(
        default=3,
        validation_alias=AliasChoices("CC_WARC_MAX_RETRIES", "CC_S3_MAX_RETRIES"),
        ge=1,
        description="Attempts for transient Common Crawl WARC download failures.",
    )
    cc_warc_retry_delay_seconds: float = Field(
        default=1.5,
        validation_alias=AliasChoices(
            "CC_WARC_RETRY_DELAY_SECONDS",
            "CC_S3_RETRY_DELAY",
        ),
        ge=0,
        description="Initial exponential retry delay for transient CC WARC failures.",
    )
    cc_input_backend: str = Field(
        default="prod",
        validation_alias="CC_INPUT_BACKEND",
    )
    # ── Dataset publish / Kaggle sync ─────────────────────────────────────────
    kaggle_username: str | None = Field(default=None, validation_alias="KAGGLE_USERNAME")
    kaggle_key: str | None = Field(default=None, validation_alias="KAGGLE_API_TOKEN")
    kaggle_dataset_slug: str | None = Field(default=None, validation_alias="KAGGLE_DATASET_SLUG")
    github_ml_repo_owner: str | None = Field(
        default=None, validation_alias="SICURRE_GITHUB_ML_REPO_OWNER"
    )
    github_ml_repo_name: str = "sicurre-ml"
    github_ml_dispatch_token: str | None = Field(
        default=None, validation_alias="SICURRE_GITHUB_ML_DISPATCH_TOKEN"
    )
    internal_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTERNAL_API_KEY", "SICURRE_INTERNAL_API_KEY"),
    )
    inference_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SICURRE_INFERENCE_API_KEY", "INFERENCE_API_KEY"),
    )
    inference_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SICURRE_INFERENCE_API_URL", "INFERENCE_API_URL"),
    )
    # Public base URL of this API (used by Cloudflare Workers to call back)
    # Must be reachable from the internet, e.g. https://api.yourdomain.com
    public_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PUBLIC_API_URL", "SICURRE_PUBLIC_API_URL"),
    )
    internal_app_probe_url: str | None = Field(
        default=None,
        validation_alias="SICURRE_INTERNAL_APP_PROBE_URL",
        description="Private app gateway base URL used only by runtime health probes.",
    )
    scheduler_enabled: bool = False
    telemetry_traces_enabled: bool = False
    telemetry_otlp_endpoint: str = "http://alloy:4318/v1/traces"
    telemetry_trace_sample_ratio: float = Field(default=1.0, ge=0, le=1)
    operational_tests_enabled: bool = False
    operational_test_max_duration_seconds: int = Field(default=600, ge=120, le=1800)
    scheduler_interval_seconds: int = Field(
        default=604800,
        validation_alias="SICURRE_SCHEDULER_INTERVAL_SECONDS",
        ge=60,
        description="Legacy in-process scheduler interval; production uses source-specific host cron.",
    )
    sla_latency_ms: int = 10000

    # Google OAuth credentials configuration
    google_client_id: str | None = Field(
        default=None,
        validation_alias="GOOGLE_CLIENT_ID",
    )
    google_client_secret: str | None = Field(
        default=None,
        validation_alias="GOOGLE_CLIENT_SECRET",
    )
    google_redirect_uri: str | None = Field(
        default=None,
        validation_alias="GOOGLE_REDIRECT_URI",
    )

    # Loops Email API Configuration
    loops_api_key: str | None = Field(default=None, validation_alias="LOOPS_API_KEY")
    loops_sign_up_transaction_id: str | None = Field(
        default=None, validation_alias="LOOPS_SIGN_UP_TRANSACTION_ID"
    )
    loops_reset_password_transaction_id: str | None = Field(
        default=None, validation_alias="LOOPS_RESET_PASSWORD_TRANSACTION_ID"
    )
    loops_threat_quarantined_transaction_id: str | None = Field(
        default=None, validation_alias="LOOPS_THREAT_QUARANTINED_TRANSACTION_ID"
    )
    loops_dns_shield_alert_transaction_id: str | None = Field(
        default=None, validation_alias="LOOPS_DNS_SHIELD_ALERT_TRANSACTION_ID"
    )
    loops_emergency_lockdown_transaction_id: str | None = Field(
        default=None, validation_alias="LOOPS_EMERGECNY_LOCKDOWN_TRANSACTION_ID"
    )
    loops_quota_warning_transaction_id: str | None = Field(
        default=None, validation_alias="LOOPS_QUOTA_WARNING_TRANSACTION_ID"
    )

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        env_prefix="SICURRE_",
        extra="ignore",
    )

    @field_validator("inference_api_url", "public_api_url")
    @classmethod
    def _validate_runtime_url(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        """Reject malformed public and inference endpoint URLs at startup."""
        if value is None:
            return value
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None

        parsed = urlparse(normalized)
        hostname = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not hostname:
            raise ValueError(f"{info.field_name} must be an absolute HTTP(S) URL")
        if (
            "." not in hostname
            and hostname not in {"localhost"}
            and not hostname.startswith("127.")
        ):
            raise ValueError(
                f"{info.field_name} host '{hostname}' is not valid; use a real host such as api.sicurre.com"
            )

        path = parsed.path.rstrip("/")
        if info.field_name == "inference_api_url" and path != "/v1/classify":
            raise ValueError(
                "inference_api_url must point to the classifier endpoint ending in /v1/classify"
            )
        if info.field_name == "public_api_url" and path in {"/v1/classify", "/v1/email/scan"}:
            raise ValueError(
                "public_api_url must be the public Sicurre app API base URL, not a /v1 endpoint"
            )
        return normalized

    @field_validator("better_auth_schema")
    @classmethod
    def _validate_better_auth_schema(cls, value: str) -> str:
        """Allow only an unambiguous PostgreSQL schema identifier."""
        normalized = value.strip().lower()
        if re.fullmatch(r"[a-z_][a-z0-9_]*", normalized) is None:
            raise ValueError("better_auth_schema must be a safe PostgreSQL identifier")
        return normalized

    @model_validator(mode="after")
    def _validate_production_secret_encryption(self) -> Settings:
        """Require a valid, dedicated encryption key for production secrets."""
        from core.secret_cipher import encrypt_secret

        if self.environment.lower() in {"production", "prod"}:
            encrypt_secret(
                "startup-validation",
                configured_key=self.secret_encryption_key,
                environment=self.environment,
            )
        return self

    @property
    def sync_database_url(self) -> str:
        """Return the main database URL with a synchronous SQLAlchemy driver."""
        match True:
            case _ if self.database_url.startswith("sqlite+aiosqlite://"):
                return self.database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
            case _ if self.database_url.startswith("postgresql+asyncpg://"):
                return self.database_url.replace(
                    "postgresql+asyncpg://", "postgresql+psycopg://", 1
                )
            case _:
                return self.database_url

    @property
    def sync_data_platform_database_url(self) -> str:
        """Return the data-platform URL with a synchronous SQLAlchemy driver."""
        if self.data_platform_database_url.startswith("sqlite+aiosqlite://"):
            return self.data_platform_database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        # postgresql+psycopg:// is valid for both sync and async with psycopg3
        return self.data_platform_database_url

    def resolve_snapshot_storage_backend(self, *, source_key: str | None = None) -> str:
        """Return the effective snapshot backend for an optional source override."""
        override = self._resolve_source_snapshot_override(
            source_key=source_key,
            setting_name="storage_backend",
        )
        backend = override or self.raw_snapshot_storage_backend
        return str(backend).strip().lower()

    def _resolve_source_snapshot_override(
        self,
        *,
        source_key: str | None,
        setting_name: str,
    ) -> str | Path | None:
        """Read a source-scoped snapshot setting when the model exposes it."""
        if not source_key:
            return None

        normalized_source_key = source_key.strip().lower().replace("-", "_").replace(" ", "_")
        attribute_name = f"{normalized_source_key}_snapshot_{setting_name}"
        return getattr(self, attribute_name, None)

    @property
    def dev_bearer_tokens(self) -> frozenset[str]:
        """Return normalized development bearer tokens."""
        return frozenset(
            token.strip() for token in self.auth_dev_bearer_tokens.split(",") if token.strip()
        )

    @property
    def allow_dev_tokens(self) -> bool:
        """Whether development bearer tokens are allowed in this environment."""
        if self.auth_allow_dev_tokens is not None:
            return self.auth_allow_dev_tokens
        return self.environment in {"dev", "test"}

    @property
    def platform_admin_email_set(self) -> frozenset[str]:
        """Return normalized platform administrator email addresses."""
        return frozenset(
            email.strip().lower()
            for email in self.platform_admin_emails.split(",")
            if email.strip()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached settings instance."""
    return Settings()
