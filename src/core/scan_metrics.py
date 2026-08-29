"""Prometheus metrics for the email scan decision path.

The SLA is stated end to end ("temps de réponse global < 2.0 s"), but until now
nothing exported the time to reach a verdict. The only latency series reaching
Grafana was generic HTTP request duration, which is why the dashboard read
~1.5 s while the stored inference events said ~3.75 s.

Two instruments, deliberately separated:

* ``sicurre_scan_duration_seconds`` — the whole decision, the number the
  customer-facing SLA is judged on.
* ``sicurre_scan_stage_duration_seconds`` — the same request split by stage, so
  a breach can be attributed instead of guessed at.

Buckets straddle the 2 s objective closely enough to read compliance directly
off the histogram, and extend far enough to keep provider stalls visible rather
than collapsed into +Inf.
"""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator

from prometheus_client import Counter, Histogram

# 2.0 is the SLA. The neighbours around it exist so "just inside" and "just
# outside" are distinguishable without re-deploying.
_SCAN_BUCKETS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 10.0, 30.0)
_STAGE_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 5.0, 10.0)

scan_duration = Histogram(
    "sicurre_scan_duration_seconds",
    "End-to-end time to reach an email verdict, as measured by the scan handler.",
    ("verdict",),
    buckets=_SCAN_BUCKETS,
)

scan_stage_duration = Histogram(
    "sicurre_scan_stage_duration_seconds",
    "Time spent in one stage of the scan decision path.",
    ("stage",),
    buckets=_STAGE_BUCKETS,
)

scan_sla_breach_total = Counter(
    "sicurre_scan_sla_breach_total",
    "Scans whose end-to-end decision exceeded the configured SLA.",
    ("verdict",),
)

scan_total = Counter(
    "sicurre_scan_total",
    "Scan decisions reaching a verdict.",
    ("verdict",),
)


@contextmanager
def observe_stage(stage: str) -> Iterator[None]:
    """Time one stage. Records even when the stage raises, so a failing
    dependency shows up as slow rather than vanishing from the histogram."""
    started = perf_counter()
    try:
        yield
    finally:
        scan_stage_duration.labels(stage=stage).observe(perf_counter() - started)


def observe_scan(*, verdict: str, duration_seconds: float, sla_seconds: float) -> None:
    """Record one completed scan against the SLA."""
    label = verdict or "unknown"
    scan_duration.labels(verdict=label).observe(duration_seconds)
    scan_total.labels(verdict=label).inc()
    if sla_seconds > 0 and duration_seconds > sla_seconds:
        scan_sla_breach_total.labels(verdict=label).inc()
