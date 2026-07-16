"""Bounded HTTP load measurements for certification and staging evidence."""

from __future__ import annotations

import asyncio
import math
import time
from collections import Counter
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class LoadAuditConfig:
    """Validated inputs for one bounded HTTP load audit."""

    url: str
    request_count: int = 100
    concurrency: int = 10
    timeout_seconds: float = 10.0
    expected_status: int = 200

    def __post_init__(self) -> None:
        """Reject unsafe or nonsensical benchmark parameters."""
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("Load-audit URL must use HTTP or HTTPS.")
        if not 1 <= self.request_count <= 10_000:
            raise ValueError("request_count must be between 1 and 10000.")
        if not 1 <= self.concurrency <= min(self.request_count, 500):
            raise ValueError("concurrency must be between 1 and request_count (max 500).")
        if not 0.1 <= self.timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 0.1 and 120.")


@dataclass(frozen=True)
class LoadAuditResult:
    """Aggregate outcome of one load audit without response payload retention."""

    request_count: int
    success_count: int
    duration_seconds: float
    latencies_ms: tuple[float, ...]
    status_counts: dict[str, int]

    @property
    def error_count(self) -> int:
        """Return requests that did not meet the configured success contract."""
        return self.request_count - self.success_count

    @property
    def error_rate(self) -> float:
        """Return the failed-request ratio in the closed interval zero to one."""
        return self.error_count / self.request_count

    @property
    def throughput_per_second(self) -> float:
        """Return total completed requests per elapsed second."""
        return self.request_count / self.duration_seconds

    @property
    def average_ms(self) -> float:
        """Return average successful-request latency."""
        return sum(self.latencies_ms) / len(self.latencies_ms)

    def percentile_ms(self, percentile: float) -> float:
        """Return a nearest-rank percentile from successful requests."""
        if not self.latencies_ms:
            raise ValueError("No successful latency samples are available.")
        if not 0 < percentile <= 100:
            raise ValueError("percentile must be greater than zero and at most 100.")
        ordered = sorted(self.latencies_ms)
        rank = max(1, math.ceil((percentile / 100) * len(ordered)))
        return ordered[rank - 1]

    def meets(self, *, max_error_rate: float, max_p95_ms: float) -> bool:
        """Return whether the result satisfies explicit release thresholds."""
        if not 0 <= max_error_rate <= 1 or max_p95_ms <= 0:
            raise ValueError("Invalid load-audit thresholds.")
        return (
            bool(self.latencies_ms)
            and self.error_rate <= max_error_rate
            and self.percentile_ms(95) <= max_p95_ms
        )


async def run_load_audit(
    config: LoadAuditConfig,
    *,
    headers: dict[str, str] | None = None,
) -> LoadAuditResult:
    """Issue bounded concurrent GET requests and retain only aggregate metadata."""
    semaphore = asyncio.Semaphore(config.concurrency)
    latencies: list[float] = []
    statuses: Counter[str] = Counter()

    async with httpx.AsyncClient(timeout=config.timeout_seconds, headers=headers) as client:

        async def send_request() -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(config.url)
                except httpx.HTTPError as error:
                    statuses[f"error:{type(error).__name__}"] += 1
                    return
                statuses[str(response.status_code)] += 1
                if response.status_code == config.expected_status:
                    latencies.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        await asyncio.gather(*(send_request() for _ in range(config.request_count)))
        duration = max(time.perf_counter() - started, 1e-9)

    return LoadAuditResult(
        request_count=config.request_count,
        success_count=len(latencies),
        duration_seconds=duration,
        latencies_ms=tuple(latencies),
        status_counts=dict(sorted(statuses.items())),
    )
