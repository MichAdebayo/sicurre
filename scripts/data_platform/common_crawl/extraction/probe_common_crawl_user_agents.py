from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "tasks/reviews/common_crawl_user_agent_probe.json"
PROBES = [
    ("CC-MAIN-2024-42", "zataz.com/*"),
    ("CC-MAIN-2024-42", "www.labanquepostale.fr/*"),
    ("CC-MAIN-2024-42", "*.cdiscount.com/newsletter*"),
]
USER_AGENTS = {
    "chrome_macos": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "firefox_macos": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:137.0) Gecko/20100101 Firefox/137.0",
    "curl": "curl/8.7.1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Common Crawl index responses across multiple user agents"
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


async def fetch_once(
    client: httpx.AsyncClient, crawl_id: str, pattern: str, user_agent: str
) -> dict[str, object]:
    url = f"https://index.commoncrawl.org/{crawl_id}-index"
    params = {"url": pattern, "output": "json", "limit": "10"}
    started = datetime.now(timezone.utc).isoformat()
    try:
        response = await client.get(
            url, params=params, headers={"User-Agent": user_agent}
        )
        body = response.text.splitlines()
        return {
            "started_at": started,
            "status_code": response.status_code,
            "line_count": len(body),
            "first_line": body[0][:200] if body else "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "started_at": started,
            "error": type(exc).__name__,
            "message": str(exc),
        }


async def main() -> None:
    args = parse_args()
    output_path = args.output_json
    limits = httpx.Limits(max_keepalive_connections=1, max_connections=2)
    timeout = httpx.Timeout(25.0)
    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [],
    }
    async with httpx.AsyncClient(
        limits=limits, timeout=timeout, follow_redirects=True
    ) as client:
        for crawl_id, pattern in PROBES:
            result = {"crawl_id": crawl_id, "pattern": pattern, "user_agents": {}}
            for name, user_agent in USER_AGENTS.items():
                result["user_agents"][name] = await fetch_once(
                    client, crawl_id, pattern, user_agent
                )
                await asyncio.sleep(2)
            payload["results"].append(result)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())