"""Run a bounded, thresholded load audit against one Sicurre HTTP endpoint."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

from data_platform.services.shared.load_audit import LoadAuditConfig, run_load_audit

ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def parse_args() -> argparse.Namespace:
    """Parse bounded load parameters and explicit pass thresholds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=10)
    parser.add_argument("--expected-status", type=int, default=200)
    parser.add_argument("--bearer-env")
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, required=True)
    return parser.parse_args()


def bearer_headers(environment_name: str | None) -> dict[str, str] | None:
    """Resolve an optional bearer token without accepting or printing its value."""
    if not environment_name:
        return None
    if not ENV_NAME_PATTERN.fullmatch(environment_name):
        raise ValueError("--bearer-env must be an uppercase environment variable name.")
    token = os.environ.get(environment_name)
    if not token:
        raise ValueError(f"Required bearer environment variable is absent: {environment_name}")
    return {"Authorization": f"Bearer {token}"}


async def run() -> int:
    """Execute the audit, print aggregate evidence, and enforce its gates."""
    args = parse_args()
    config = LoadAuditConfig(
        url=args.url,
        request_count=args.requests,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout_seconds,
        expected_status=args.expected_status,
    )
    result = await run_load_audit(config, headers=bearer_headers(args.bearer_env))
    print("=== Sicurre load audit ===")
    print(f"Target: {config.url}")
    print(f"Requests: {result.request_count}")
    print(f"Concurrency: {config.concurrency}")
    print(f"Duration: {result.duration_seconds:.3f}s")
    print(f"Throughput: {result.throughput_per_second:.2f} req/s")
    print(f"Successes: {result.success_count}; errors: {result.error_count}")
    print(f"Status counts: {result.status_counts}")
    if result.latencies_ms:
        print(f"Average: {result.average_ms:.2f}ms")
        print(f"p50: {result.percentile_ms(50):.2f}ms")
        print(f"p95: {result.percentile_ms(95):.2f}ms")
        print(f"p99: {result.percentile_ms(99):.2f}ms")
    passed = result.meets(
        max_error_rate=args.max_error_rate,
        max_p95_ms=args.max_p95_ms,
    )
    print(f"Gate: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run()))
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
