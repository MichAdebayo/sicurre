"""Run Domain Shield DNS sync for a configured Cloudflare domain.

This maintenance script uses the app-stored Cloudflare token and does not print
the token. It is intended for local verification/recovery of DNS provisioning.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from data_platform.api.routers.integrations import _sync_domain_shield_dns  # noqa: E402
from data_platform.services.cloudflare_provisioner import CloudflareProvisioner  # noqa: E402


def _load_integration(domain: str) -> sqlite3.Row:
    conn = sqlite3.connect(ROOT / "data/local/sicurre.db")
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT workspace_id, api_token
            FROM cloudflare_integration
            WHERE zone_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (domain,),
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row["api_token"]:
        raise RuntimeError(f"No stored Cloudflare token found for {domain}")
    return row


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("domain")
    parser.add_argument("--spf", action="store_true")
    parser.add_argument("--dkim", action="store_true")
    parser.add_argument("--dmarc", action="store_true")
    args = parser.parse_args()

    row = _load_integration(args.domain)
    result = await _sync_domain_shield_dns(
        provisioner=CloudflareProvisioner(api_token=row["api_token"]),
        workspace_id=row["workspace_id"],
        zone_name=args.domain,
        fix_spf=args.spf,
        fix_dkim=args.dkim,
        fix_dmarc=args.dmarc,
    )
    print(
        {
            "dmarc_record": result["dmarc_record"],
            "dmarc_reporting_enabled": result["dmarc_reporting_enabled"],
            "reputation_score": result["reputation_score"],
            "score_grade": result["score_grade"],
        }
    )


if __name__ == "__main__":
    asyncio.run(_main())
