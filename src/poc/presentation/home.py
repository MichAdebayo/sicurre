"""Home dashboard metrics and rendering for the certification POC."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import streamlit as st

from poc.presentation.formatting import (
    effective_label,
    effective_verdict,
    format_number,
    safe_text,
)


@dataclass(frozen=True)
class HomeMetrics:
    """Dashboard values derived from persisted inference evidence."""

    total: int
    blocked: int
    delivered: int
    spam_safe: int
    label_accuracy: float
    false_positives: int
    false_negatives: int
    latency_p95_ms: float


def calculate_home_metrics(events: list[dict[str, Any]]) -> HomeMetrics:
    """Calculate deterministic operational and evaluation metrics."""
    evaluated = [event for event in events if event.get("expected_label")]
    false_positives = sum(
        effective_verdict(event) == "phishing" and event.get("expected_label") != "phishing"
        for event in evaluated
    )
    false_negatives = sum(
        effective_verdict(event) != "phishing" and event.get("expected_label") == "phishing"
        for event in evaluated
    )
    accuracy = (
        sum(effective_label(event) == event["expected_label"] for event in evaluated)
        / len(evaluated)
        * 100.0
        if evaluated
        else 0.0
    )
    latencies = sorted(
        float(event.get("latency_ms") or 0.0)
        for event in events
        if float(event.get("latency_ms") or 0.0) > 0
    )
    p95_index = max(int(len(latencies) * 0.95) - 1, 0)
    return HomeMetrics(
        total=len(events),
        blocked=sum(effective_verdict(event) == "phishing" for event in events),
        delivered=sum(effective_verdict(event) == "safe" for event in events),
        spam_safe=sum(
            effective_verdict(event) == "safe" and effective_label(event) == "spam"
            for event in events
        ),
        label_accuracy=accuracy,
        false_positives=false_positives,
        false_negatives=false_negatives,
        latency_p95_ms=latencies[p95_index] if latencies else 0.0,
    )


def _metric_card(column: Any, label: str, value: str, color: str = "") -> None:
    color_style = f" style='color:{color};'" if color else ""
    column.markdown(
        f"<div class='kpi'><div class='label'>{label}</div>"
        f"<div class='value'{color_style}>{value}</div></div>",
        unsafe_allow_html=True,
    )


def render_home(
    user: dict[str, Any], events: list[dict[str, Any]], translate: Callable[[str], str]
) -> None:
    """Render the POC dashboard from already-loaded local evidence."""
    metrics = calculate_home_metrics(events)
    st.markdown(
        f"<h1 style='margin-bottom:4px;'>{translate('welcome')}, {user['display_name']}</h1>",
        unsafe_allow_html=True,
    )
    st.caption(translate("home_subtitle"))
    st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)

    first_row = st.columns(4)
    _metric_card(first_row[0], translate("emails_scanned"), format_number(metrics.total))
    _metric_card(
        first_row[1],
        translate("phishing_blocked"),
        format_number(metrics.blocked),
        "var(--danger-semantic)",
    )
    _metric_card(
        first_row[2],
        translate("delivered_inbox"),
        format_number(metrics.delivered),
        "var(--safe)",
    )
    _metric_card(
        first_row[3],
        translate("safe_spam"),
        format_number(metrics.spam_safe),
        "var(--warning)",
    )
    st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

    second_row = st.columns(4)
    _metric_card(second_row[0], translate("label_accuracy"), f"{metrics.label_accuracy:.1f}%")
    _metric_card(second_row[1], translate("false_positive"), str(metrics.false_positives))
    _metric_card(second_row[2], translate("false_negative"), str(metrics.false_negatives))
    _metric_card(second_row[3], translate("latency_p95"), f"{metrics.latency_p95_ms:.0f} ms")
    st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)

    st.markdown(f"#### {translate('recent_activity')}")
    if not events:
        st.info(translate("no_events"))
        return
    for event in events[:6]:
        verdict = effective_verdict(event)
        label = effective_label(event)
        if verdict == "phishing":
            badge = f"<span class='badge badge-phishing'>{translate('class_phishing')}</span>"
        elif label == "spam":
            badge = f"<span class='badge badge-spam'>{translate('class_spam')}</span>"
        else:
            badge = f"<span class='badge badge-safe'>{translate('class_legitimate')}</span>"
        timestamp = event["created_at"].replace("T", " ")[:16]
        st.markdown(
            "<div class='card' style='padding:10px 12px;margin-bottom:5px;'>"
            "<div style='font-size:0.9rem;font-weight:600;color:var(--text);'>"
            f"{safe_text(event['subject'], 60)}</div>"
            "<div style='font-size:0.78rem;color:var(--text-2);margin-top:3px;'>"
            f"{safe_text(event['sender'], 50)} &middot; {timestamp} &middot; {badge}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
