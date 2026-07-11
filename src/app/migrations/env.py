from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from core.config import get_settings

config = context.config
settings = get_settings()

if not settings.app_neon_database_url:
    raise RuntimeError(
        "SICURRE_APP_NEON_DATABASE_URL is not set. "
        "App migrations require a Neon PostgreSQL connection."
    )

config.set_main_option("sqlalchemy.url", settings.app_neon_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# App models will be imported here as they are created.
# Example: from app.models import users  # noqa: F401
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
