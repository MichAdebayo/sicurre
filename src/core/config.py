from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"


_DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{_DB_PATH.as_posix()}"


class Settings(BaseSettings):
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
    better_auth_base_url: str | None = None
    better_auth_session_path: str = "/api/auth/get-session"
    better_auth_timeout_seconds: float = 5.0
    better_auth_cookie_name: str = "better-auth.session_token"
    raw_snapshot_storage_backend: str = "local"
    raw_snapshot_local_dir: Path = ROOT_DIR / "data" / "raw" / "api"
    raw_snapshot_prefix: str = "raw-snapshots"
    raw_snapshot_r2_bucket_name: str | None = None
    raw_snapshot_r2_endpoint_url: str | None = None
    raw_snapshot_r2_access_key_id: str | None = None
    raw_snapshot_r2_secret_access_key: str | None = None
    raw_snapshot_r2_region: str = "auto"
    phishtank_api_key: str | None = None
    phishtank_user_agent: str = "phishtank/sicurre-research"
    phishtank_snapshot_storage_backend: str | None = None
    phishtank_snapshot_local_dir: Path = ROOT_DIR / "data" / "raw" / "api" / "phishtank"
    phishtank_snapshot_prefix: str = "phishtank"
    certfr_snapshot_storage_backend: str | None = None
    certfr_snapshot_prefix: str = "cert-fr"
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
    cc_input_backend: str = Field(
        default="prod",
        validation_alias="CC_INPUT_BACKEND",
    )
    # ── Dataset publish / Kaggle sync ─────────────────────────────────────────
    kaggle_username: str | None = Field(
        default=None, validation_alias="KAGGLE_USERNAME"
    )
    kaggle_key: str | None = Field(default=None, validation_alias="KAGGLE_API_TOKEN")
    kaggle_dataset_slug: str | None = Field(
        default=None, validation_alias="KAGGLE_DATASET_SLUG"
    )
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
        default=None, validation_alias="INFERENCE_API_KEY"
    )
    inference_api_url: str | None = Field(
        default=None, validation_alias="INFERENCE_API_URL"
    )
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 604800

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        env_prefix="SICURRE_",
        extra="ignore",
    )

    @property
    def sync_database_url(self) -> str:
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
        if self.data_platform_database_url.startswith("sqlite+aiosqlite://"):
            return self.data_platform_database_url.replace(
                "sqlite+aiosqlite://", "sqlite://", 1
            )
        # postgresql+psycopg:// is valid for both sync and async with psycopg3
        return self.data_platform_database_url

    def resolve_snapshot_storage_backend(self, *, source_key: str | None = None) -> str:
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
        if not source_key:
            return None

        normalized_source_key = (
            source_key.strip().lower().replace("-", "_").replace(" ", "_")
        )
        attribute_name = f"{normalized_source_key}_snapshot_{setting_name}"
        return getattr(self, attribute_name, None)

    @property
    def dev_bearer_tokens(self) -> frozenset[str]:
        return frozenset(
            token.strip()
            for token in self.auth_dev_bearer_tokens.split(",")
            if token.strip()
        )

    @property
    def allow_dev_tokens(self) -> bool:
        if self.auth_allow_dev_tokens is not None:
            return self.auth_allow_dev_tokens
        return self.environment in {"dev", "test"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
