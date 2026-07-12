"""Rebind an existing local Cloudflare Email Worker to the production API."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "src"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--scan-url", default="https://sicurre.com/v1/email/scan")
    parser.add_argument("--local-db", type=Path, default=ROOT_DIR / "data/local/sicurre.db")
    parser.add_argument("--api-env", type=Path, default=ROOT_DIR / "deploy/env.api")
    return parser.parse_args()


def _load_local_integration(db_path: Path, domain: str) -> dict[str, object]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM cloudflare_integration WHERE zone_name = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (domain,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"No local Cloudflare integration found for {domain}")
        return dict(row)
    finally:
        connection.close()


def _production_database_url(env_path: Path) -> str:
    value = dotenv_values(env_path).get("SICURRE_DATABASE_URL")
    if not value:
        raise RuntimeError("SICURRE_DATABASE_URL is missing from deploy/env.api")
    return str(value).replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _verify_production_schema(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM cloudflare_integration LIMIT 1"))
    finally:
        engine.dispose()


def _upsert_production_integration(
    database_url: str,
    integration: dict[str, object],
    shared_secret_hash: str,
) -> None:
    columns = (
        "id",
        "user_email",
        "workspace_id",
        "workspace_member_user_id",
        "zone_id",
        "zone_name",
        "account_id",
        "worker_name",
        "rule_id",
        "destination_email",
        "api_token",
        "status",
        "created_at",
        "updated_at",
    )
    values = {column: integration.get(column) for column in columns}
    values["shared_secret_hash"] = shared_secret_hash
    engine = create_engine(database_url, pool_pre_ping=True)
    statement = text(
        """
        INSERT INTO cloudflare_integration (
            id, user_email, workspace_id, workspace_member_user_id, zone_id,
            zone_name, account_id, worker_name, rule_id, destination_email,
            api_token, shared_secret_hash, status, created_at, updated_at
        ) VALUES (
            :id, :user_email, :workspace_id, :workspace_member_user_id, :zone_id,
            :zone_name, :account_id, :worker_name, :rule_id, :destination_email,
            :api_token, :shared_secret_hash, :status, :created_at, :updated_at
        )
        ON CONFLICT (id) DO UPDATE SET
            api_token = EXCLUDED.api_token,
            shared_secret_hash = EXCLUDED.shared_secret_hash,
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at
        """
    )
    try:
        with engine.begin() as connection:
            connection.execute(statement, values)
    finally:
        engine.dispose()


def _update_local_hash(db_path: Path, integration_id: str, shared_secret_hash: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE cloudflare_integration SET shared_secret_hash = ? WHERE id = ?",
            (shared_secret_hash, integration_id),
        )
        connection.commit()
    finally:
        connection.close()


async def main() -> None:
    """Rotate the Worker secret and persist its hash in local and production databases."""
    args = _parse_args()
    integration = _load_local_integration(args.local_db, args.domain)
    database_url = _production_database_url(args.api_env)
    _verify_production_schema(database_url)

    from data_platform.services.cloudflare_provisioner import CloudflareProvisioner

    shared_secret = secrets.token_urlsafe(40)
    shared_secret_hash = hashlib.sha256(shared_secret.encode()).hexdigest()
    provisioner = CloudflareProvisioner(api_token=str(integration["api_token"]))
    await provisioner.deploy_email_worker(
        account_id=str(integration["account_id"]),
        worker_name=str(integration["worker_name"]),
        scan_url=args.scan_url,
        shared_secret=shared_secret,
        forward_to=str(integration["destination_email"]),
    )
    _upsert_production_integration(database_url, integration, shared_secret_hash)
    _update_local_hash(args.local_db, str(integration["id"]), shared_secret_hash)
    print(
        {
            "domain": args.domain,
            "worker": integration["worker_name"],
            "scan_url": args.scan_url,
            "production_binding": "updated",
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
