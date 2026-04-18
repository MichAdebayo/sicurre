from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"


_DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{_DB_PATH.as_posix()}"


class Settings(BaseSettings):
    app_name: str = "Sicurre API"
    environment: str = "dev"
    database_url: str = _DEFAULT_DB_URL
    database_echo: bool = False
    database_historical_cron_total_count: int = 72
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
    phishtank_snapshot_local_dir: Path = ROOT_DIR / "data" / "raw" / "api" / "phishtank"
    phishtank_snapshot_prefix: str = "phishtank"
    cc_input_backend: str = Field(
        default="prod",
        validation_alias="CC_INPUT_BACKEND",
    )

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
