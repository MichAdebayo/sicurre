from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "tasks/reviews/common_crawl_index_probe.json"
PROBES = [
    ("CC-MAIN-2025-08", "signal-arnaques.com/*"),
    ("CC-MAIN-2024-51", "signal-arnaques.com/*"),
    ("CC-MAIN-2024-42", "zataz.com/*"),
    ("CC-MAIN-2024-42", "www.labanquepostale.fr/*"),
    ("CC-MAIN-2024-42", "*.cdiscount.com/newsletter*"),
    ("CC-MAIN-2024-22", "zataz.com/*"),
    ("CC-MAIN-2024-10", "signal-arnaques.com/*"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Common Crawl index availability with retries"
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--attempts", type=int, default=6)
    return parser.parse_args()


async def probe(crawl_id: str, pattern: str, attempts: int = 6) -> dict[str, object]:
    url = f"https://index.commoncrawl.org/{crawl_id}-index"
    params = {"url": pattern, "output": "json", "limit": "10"}
    history: list[dict[str, object]] = []
    limits = httpx.Limits(max_keepalive_connections=2, max_connections=4)
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(
        limits=limits, timeout=timeout, follow_redirects=True
    ) as client:
        for attempt in range(1, attempts + 1):
            started = datetime.now(timezone.utc).isoformat()
            try:
                response = await client.get(url, params=params)
                body = response.text.splitlines()
                history.append(
                    {
                        "attempt": attempt,
                        "started_at": started,
                        "status_code": response.status_code,
                        "line_count": len(body),
                        "first_line": body[0][:200] if body else "",
                    }
                )
                if response.status_code == 200 and body:
                    break
            except Exception as exc:  # noqa: BLE001
                history.append(
                    {
                        "attempt": attempt,
                        "started_at": started,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            await asyncio.sleep(min(10 * (2 ** (attempt - 1)), 90))
    return {"crawl_id": crawl_id, "pattern": pattern, "history": history}


async def main() -> None:
    args = parse_args()
    results = []
    for crawl_id, pattern in PROBES:
        results.append(await probe(crawl_id, pattern, attempts=args.attempts))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())