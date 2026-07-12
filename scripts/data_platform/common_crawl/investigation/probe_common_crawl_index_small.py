from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "tasks/reviews/common_crawl_index_probe_small.json"
PROBES = [
    ("CC-MAIN-2024-42", "zataz.com/*"),
    ("CC-MAIN-2024-42", "www.labanquepostale.fr/*"),
    ("CC-MAIN-2024-42", "*.cdiscount.com/newsletter*"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe a small Common Crawl index subset with incremental artifact writes"
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--attempts", type=int, default=4)
    return parser.parse_args()


def write_payload(output_path: Path, payload: dict[str, object]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def probe(
    crawl_id: str,
    pattern: str,
    payload: dict[str, object],
    *,
    output_path: Path,
    attempts: int = 4,
) -> None:
    url = f"https://index.commoncrawl.org/{crawl_id}-index"
    params = {"url": pattern, "output": "json", "limit": "10"}
    limits = httpx.Limits(max_keepalive_connections=1, max_connections=2)
    timeout = httpx.Timeout(25.0)
    history: list[dict[str, object]] = []
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
                write_payload(output_path, payload)
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
                write_payload(output_path, payload)
            if attempt < attempts:
                await asyncio.sleep(min(5 * (2 ** (attempt - 1)), 40))
    payload["results"].append(
        {"crawl_id": crawl_id, "pattern": pattern, "history": history}
    )
    write_payload(output_path, payload)


async def main() -> None:
    args = parse_args()
    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [],
        "probes": [
            {"crawl_id": crawl_id, "pattern": pattern} for crawl_id, pattern in PROBES
        ],
    }
    write_payload(args.output_json, payload)
    for crawl_id, pattern in PROBES:
        await probe(
            crawl_id,
            pattern,
            payload,
            output_path=args.output_json,
            attempts=args.attempts,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())