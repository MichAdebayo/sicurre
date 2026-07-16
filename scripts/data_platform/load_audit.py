"""Load and performance validation script for Sicurre API boundaries."""

from __future__ import annotations

import asyncio
import sys
import time

import httpx


async def benchmark_endpoint(url: str, requests_count: int, concurrency: int) -> None:
    print(f"Starting benchmark on URL: {url}")
    print(f"Total Requests: {requests_count} | Concurrency Level: {concurrency}\n")

    latencies: list[float] = []
    errors_count = 0
    success_count = 0

    semaphore = asyncio.Semaphore(concurrency)
    client = httpx.AsyncClient(timeout=10.0)

    async def send_request() -> None:
        nonlocal errors_count, success_count
        async with semaphore:
            start_time = time.monotonic()
            try:
                r = await client.get(url)
                duration = time.monotonic() - start_time
                if r.status_code == 200:
                    success_count += 1
                    latencies.append(duration * 1000.0)  # convert to ms
                else:
                    errors_count += 1
            except Exception:
                errors_count += 1

    start_bench = time.monotonic()
    tasks = [asyncio.create_task(send_request()) for _ in range(requests_count)]
    await asyncio.gather(*tasks)
    await client.aclose()

    total_bench_duration = time.monotonic() - start_bench

    if not latencies:
        print("Error: All requests failed. No latency data gathered.")
        sys.exit(1)

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = sum(latencies) / len(latencies)

    print("=== Load Audit Results ===")
    print(f"Duration: {total_bench_duration:.2f} seconds")
    print(f"Throughput: {requests_count / total_bench_duration:.2f} req/sec")
    print(f"Successes: {success_count} | Errors: {errors_count}")
    print(f"Average Latency: {avg:.2f} ms")
    print(f"p50 (Median)   : {p50:.2f} ms")
    print(f"p95 Latency    : {p95:.2f} ms")
    print(f"p99 Latency    : {p99:.2f} ms")
    print("==========================")


if __name__ == "__main__":
    url_target = "http://localhost:8000/health"
    reqs = 100
    conn = 10

    if len(sys.argv) > 1:
        url_target = sys.argv[1]
    if len(sys.argv) > 2:
        reqs = int(sys.argv[2])
    if len(sys.argv) > 3:
        conn = int(sys.argv[3])

    asyncio.run(benchmark_endpoint(url_target, reqs, conn))
