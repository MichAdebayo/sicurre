from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    app_name: str = "Sicurre API"
    environment: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./backend/dev.db"
    database_echo: bool = False
    auth_enabled: bool = True
    auth_allow_dev_tokens: bool | None = None
    auth_dev_bearer_tokens: str = "dev-token,dev-rate-limit"
    better_auth_base_url: str | None = None
    better_auth_session_path: str = "/api/auth/get-session"
    better_auth_timeout_seconds: float = 5.0
    better_auth_cookie_name: str = "better-auth.session_token"

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
