"""Validated configuration contract for the local Sicurre POC."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
LOCAL_DATA_DIR = ROOT_DIR / "data" / "local"


def sqlite_path(database_url: str) -> Path:
    """Resolve a SQLite URL to its local filesystem path."""
    normalized = database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    parsed = urlsplit(normalized)
    if parsed.scheme != "sqlite" or not parsed.path:
        raise ValueError("POC database URLs must use SQLite.")
    filesystem_path = parsed.path
    if filesystem_path.startswith("//"):
        filesystem_path = filesystem_path[1:]
    path = Path(filesystem_path)
    return path if path.is_absolute() else (ROOT_DIR / path).resolve()


class PocSettings(BaseSettings):
    """Environment settings reserved for the local certification POC."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{LOCAL_DATA_DIR / 'sicurre_poc.db'}",
        validation_alias="SICURRE_POC_DATABASE_URL",
    )
    data_platform_database_url: str = Field(
        default=f"sqlite+aiosqlite:///{LOCAL_DATA_DIR / 'sicurre_dataplatform.db'}",
        validation_alias="SICURRE_POC_DATA_PLATFORM_DATABASE_URL",
    )
    inference_api_url: str = Field(
        default="http://127.0.0.1:8000/v1/classify",
        validation_alias="SICURRE_POC_INFERENCE_API_URL",
    )
    inference_api_key: str = Field(
        default="",
        validation_alias="SICURRE_POC_INFERENCE_API_KEY",
    )
    admin_email: str = Field(
        default="admin.local@sicurre.test",
        validation_alias="SICURRE_POC_ADMIN_EMAIL",
    )
    admin_password: str = Field(default="", validation_alias="SICURRE_POC_ADMIN_PASSWORD")
    admin_name: str = Field(
        default="Administrateur Sicurre",
        validation_alias="SICURRE_POC_ADMIN_NAME",
    )
    viewer_email: str = Field(
        default="viewer.local@sicurre.test",
        validation_alias="SICURRE_POC_VIEWER_EMAIL",
    )
    viewer_password: str = Field(default="", validation_alias="SICURRE_POC_VIEWER_PASSWORD")
    viewer_name: str = Field(
        default="Utilisateur Démo",
        validation_alias="SICURRE_POC_VIEWER_NAME",
    )
    snapshot_prefix: str = Field(
        default="demonstrations/poc",
        validation_alias="SICURRE_POC_SNAPSHOT_PREFIX",
    )
    snapshot_dir: Path = Field(
        default=LOCAL_DATA_DIR / "poc" / "snapshots",
        validation_alias="SICURRE_POC_SNAPSHOT_DIR",
    )
    @field_validator("database_url", "data_platform_database_url")
    @classmethod
    def validate_sqlite_url(cls, value: str) -> str:
        """Reject remote or ambiguous databases in the local POC."""
        sqlite_path(value)
        return value

    @field_validator("inference_api_url")
    @classmethod
    def validate_inference_url(cls, value: str) -> str:
        """Require the canonical local classifier endpoint."""
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or parsed.path.rstrip("/") != "/v1/classify":
            raise ValueError("SICURRE_POC_INFERENCE_API_URL must end with /v1/classify.")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("SICURRE_POC_INFERENCE_API_URL must target the local machine.")
        return value.rstrip("/")

    @field_validator("snapshot_prefix")
    @classmethod
    def validate_demo_prefix(cls, value: str) -> str:
        """Keep POC snapshots outside production cron namespaces."""
        normalized = value.strip().strip("/")
        if not normalized.startswith("demonstrations/"):
            raise ValueError("SICURRE_POC_SNAPSHOT_PREFIX must start with demonstrations/.")
        return normalized

    @property
    def auth_database_path(self) -> Path:
        """Return the local POC authentication database path."""
        return sqlite_path(self.database_url)

    @property
    def data_platform_database_path(self) -> Path:
        """Return the local POC data-platform database path."""
        return sqlite_path(self.data_platform_database_url)

    def require_demo_credentials(self) -> None:
        """Fail startup when required local demonstration secrets are absent."""
        missing = []
        if not self.admin_password:
            missing.append("SICURRE_POC_ADMIN_PASSWORD")
        if not self.viewer_password:
            missing.append("SICURRE_POC_VIEWER_PASSWORD")
        if not self.inference_api_key:
            missing.append("SICURRE_POC_INFERENCE_API_KEY")
        if missing:
            raise RuntimeError(f"Missing POC settings: {', '.join(missing)}")


@lru_cache(maxsize=1)
def get_poc_settings() -> PocSettings:
    """Return the cached local POC settings."""
    return PocSettings()
