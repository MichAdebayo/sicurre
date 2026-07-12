from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "tasks/reviews/common_crawl_query_probe.json"
PROBES = [
    ("CC-MAIN-2025-08", "signal-arnaques.com/*"),
    ("CC-MAIN-2025-08", "cybermalveillance.gouv.fr/*"),
    ("CC-MAIN-2025-08", "urlscan.io/result/*"),
    ("CC-MAIN-2025-08", "signal-spam.fr/*"),
    ("CC-MAIN-2025-08", "openphish.com/*"),
    ("CC-MAIN-2025-08", "abuse.ch/*"),
    ("CC-MAIN-2024-42", "signal-arnaques.com/*"),
    ("CC-MAIN-2024-42", "urlscan.io/result/*"),
    ("CC-MAIN-2024-42", "cybermalveillance.gouv.fr/*"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe the current Common Crawl query patterns against selected crawl indices"
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    output_path = args.output_json
    results = []
    timeout = httpx.Timeout(20.0)
    limits = httpx.Limits(max_keepalive_connections=2, max_connections=4)
    async with httpx.AsyncClient(
        timeout=timeout, limits=limits, follow_redirects=True
    ) as client:
        for crawl_id, pattern in PROBES:
            url = f"https://index.commoncrawl.org/{crawl_id}-index"
            try:
                response = await client.get(
                    url,
                    params={"url": pattern, "output": "json", "limit": "20"},
                )
                lines = response.text.splitlines()
                results.append(
                    {
                        "crawl_id": crawl_id,
                        "pattern": pattern,
                        "status_code": response.status_code,
                        "line_count": len(lines),
                        "first_line": lines[0][:160] if lines else "",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "crawl_id": crawl_id,
                        "pattern": pattern,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }
                )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())