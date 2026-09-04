"""A failed scan must be counted, not absent.

`observe_scan` runs after a verdict exists. Every path that fails before a
verdict — the classifier unreachable, a malformed response — used to return
without touching any scan instrument, so the request did not appear in
`sicurre_scan_total` as a failure; it did not appear at all.

That is the metric-level form of incident 06. The outage lasted as long as it
did because nothing counted the scans that never happened, and the only
alert covering the surface needs twenty requests in fifteen minutes before it
can fire — a threshold demo traffic never reaches.
"""

from __future__ import annotations

import json
from pathlib import Path

from core import scan_metrics

ALERTS = Path("deploy/grafana/alerts/sicurre-alerts.json")


def _failure_count(reason: str) -> float:
    return scan_metrics.scan_failure_total.labels(reason=reason)._value.get()


def test_a_failure_is_recorded_under_its_reason() -> None:
    before = _failure_count("inference_unavailable")
    scan_metrics.observe_scan_failure("inference_unavailable")
    assert _failure_count("inference_unavailable") == before + 1


def test_an_unrecognised_reason_collapses_to_unknown() -> None:
    """The label set stays closed."""
    before = _failure_count("unknown")
    scan_metrics.observe_scan_failure("https://ml.internal/v1/classify failed for bob@corp.fr")
    assert _failure_count("unknown") == before + 1


def test_the_alert_can_fire_at_demo_volume() -> None:
    """The rule must not inherit the 5xx rule's minimum-volume guard."""
    rules = {r["uid"]: r for r in json.loads(ALERTS.read_text())["rules"]}
    rule = rules["sicurre-scan-failing"]

    assert rule["threshold"] <= 5, "the threshold must be reachable at low volume"
    assert "sicurre_scan_failure_total" in rule["expression"]
    assert ">= 20" not in rule["expression"] and "clamp_min" not in rule["expression"]


def test_the_runbook_points_at_the_probe_that_distinguishes_the_cause() -> None:
    """A runbook naming the component makes the alert actionable in one step."""
    rules = {r["uid"]: r for r in json.loads(ALERTS.read_text())["rules"]}
    runbook = rules["sicurre-scan-failing"]["runbook"]

    assert "inference_contract" in runbook
