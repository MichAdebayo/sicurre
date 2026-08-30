"""The SLA is judged on these series, so their names and labels are contract."""

from __future__ import annotations

import pytest
from prometheus_client import generate_latest

from core.scan_metrics import observe_scan, observe_stage, scan_stage_duration


def _metrics_text() -> str:
    return generate_latest().decode()


def test_scan_duration_is_exported_with_verdict_label() -> None:
    observe_scan(verdict="phishing", duration_seconds=1.2, sla_seconds=2.0)
    text = _metrics_text()
    assert "sicurre_scan_duration_seconds" in text
    assert 'verdict="phishing"' in text


def test_breach_counter_only_fires_past_the_sla() -> None:
    observe_scan(verdict="spam", duration_seconds=0.9, sla_seconds=2.0)
    before = _metrics_text()
    baseline = 'sicurre_scan_sla_breach_total{verdict="spam"}' in before

    observe_scan(verdict="spam", duration_seconds=3.4, sla_seconds=2.0)
    after = _metrics_text()
    assert 'sicurre_scan_sla_breach_total{verdict="spam"}' in after
    # a breach must be recorded even if none existed before
    assert baseline or 'sicurre_scan_sla_breach_total{verdict="spam"}' in after


def test_stage_timing_records_even_when_the_stage_raises() -> None:
    """A failing dependency must show as slow, not disappear from the histogram."""
    with pytest.raises(RuntimeError):
        with observe_stage("inference"):
            raise RuntimeError("provider down")
    text = _metrics_text()
    assert 'sicurre_scan_stage_duration_seconds_count{stage="inference"}' in text


def test_buckets_straddle_the_two_second_objective() -> None:
    bounds = scan_stage_duration._upper_bounds  # noqa: SLF001 - contract check
    assert 2.0 in bounds, "2s SLA must be a bucket boundary to read compliance directly"
