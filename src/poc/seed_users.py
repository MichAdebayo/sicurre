"""Seed the default admin user for the Streamlit POC."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import logging
import os

import bcrypt
from dotenv import load_dotenv

# Load .env before any os.environ reads so POC credentials are available
load_dotenv(ROOT_DIR / ".env", override=False)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from core.database import Base
from db.models import PocUser, UserRole

logger = logging.getLogger(__name__)

# ── POC seed credentials — read from environment, never hardcoded ──────────
_FALLBACK_ADMIN_EMAIL = "admin@sicurre.fr"
_FALLBACK_ADMIN_NAME = "Administrateur Sicurre"
_FALLBACK_VIEWER_EMAIL = "demo@sicurre.fr"
_FALLBACK_VIEWER_NAME = "Utilisateur Démo"

DEFAULT_ADMIN_EMAIL = os.environ.get("SICURRE_POC_ADMIN_EMAIL", _FALLBACK_ADMIN_EMAIL)
DEFAULT_ADMIN_PASSWORD = os.environ[
    "SICURRE_POC_ADMIN_PASSWORD"
]  # required — no default
DEFAULT_ADMIN_NAME = os.environ.get("SICURRE_POC_ADMIN_NAME", _FALLBACK_ADMIN_NAME)

DEFAULT_VIEWER_EMAIL = os.environ.get(
    "SICURRE_POC_VIEWER_EMAIL", _FALLBACK_VIEWER_EMAIL
)
DEFAULT_VIEWER_PASSWORD = os.environ[
    "SICURRE_POC_VIEWER_PASSWORD"
]  # required — no default
DEFAULT_VIEWER_NAME = os.environ.get("SICURRE_POC_VIEWER_NAME", _FALLBACK_VIEWER_NAME)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def seed_users() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with session_factory() as session:
        for email, password, name, role in [
            (
                DEFAULT_ADMIN_EMAIL,
                DEFAULT_ADMIN_PASSWORD,
                DEFAULT_ADMIN_NAME,
                UserRole.ADMIN,
            ),
            (
                DEFAULT_VIEWER_EMAIL,
                DEFAULT_VIEWER_PASSWORD,
                DEFAULT_VIEWER_NAME,
                UserRole.VIEWER,
            ),
        ]:
            existing = await session.scalar(
                select(PocUser).where(PocUser.email == email)
            )
            if existing:
                print(f"  User {email} already exists — skipping.")
                continue

            user = PocUser(
                email=email,
                display_name=name,
                password_hash=hash_password(password),
                role=role.value,
            )
            session.add(user)
            print(f"  Created {role.value} user: {email}")

        await session.commit()

    await engine.dispose()
    print("User seeding complete.")


if __name__ == "__main__":
    asyncio.run(seed_users())
