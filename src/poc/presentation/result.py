"""Inference-result presentation for the local POC."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import streamlit as st


@dataclass(frozen=True)
class ResultStyle:
    """Semantic card treatment for an inference result."""

    card_class: str
    badge_class: str
    label_key: str


def result_style(result: dict[str, Any]) -> ResultStyle:
    """Map safety and classifier labels to semantic display treatment."""
    if result["safety_verdict"] == "phishing":
        return ResultStyle("result-phishing", "badge-phishing", "class_phishing")
    if result["label_verdict"] == "spam":
        return ResultStyle("result-spam", "badge-spam", "class_spam")
    return ResultStyle("result-safe", "badge-safe", "class_legitimate")


def confidence_bar(label: str, percentage: float, color: str) -> str:
    """Return bounded confidence-bar markup."""
    width = min(max(percentage, 0.0), 100.0)
    return (
        "<div style='margin-bottom:8px;'>"
        "<div style='display:flex;justify-content:space-between;margin-bottom:2px;'>"
        f"<span style='font-size:0.82rem;color:var(--text-2);'>{label}</span>"
        f"<span style='font-size:0.82rem;font-weight:700;color:{color};'>"
        f"{percentage:.0f} %</span></div>"
        "<div style='height:6px;border-radius:3px;background:var(--border);overflow:hidden;'>"
        f"<div style='width:{width}%;height:100%;background:{color};border-radius:3px;'>"
        "</div></div></div>"
    )


def render_inference_result(result: dict[str, Any], translate: Callable[[str], str]) -> None:
    """Render semantic verdict, confidence distribution, and stage evidence."""
    style = result_style(result)
    score = float(result["composite_score"]) * 100.0
    latency = float(result.get("latency_ms") or 0.0)
    explanation = result.get("explanation") or translate("no_explanation")
    colors = {"phishing": "#DC2626", "spam": "#B45309", "legitimate": "#047857"}
    labels = {
        "phishing": translate("class_phishing"),
        "spam": translate("class_spam"),
        "legitimate": translate("class_legitimate"),
    }
    distribution = result.get("label_distribution") or {}
    bars = "".join(
        confidence_bar(labels[label], float(distribution[label]) * 100.0, colors[label])
        for label in ("phishing", "spam", "legitimate")
        if label in distribution
    )
    st.markdown(
        f"""
<div class='result-card {style.card_class}'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>
    <span class='badge {style.badge_class}'>{translate(style.label_key)}</span>
    <span style='font-size:0.8rem;color:var(--text-muted);'>Score {score:.1f} % | {latency:.0f} ms</span>
  </div>
  <div style='margin-bottom:12px;'>
    <div style='font-size:0.78rem;color:var(--text-2);margin-bottom:4px;font-weight:600;text-transform:uppercase;'>{translate("explanation")}</div>
    <p style='font-size:0.9rem;color:var(--text);margin:0;'>{explanation}</p>
  </div>
  <div style='font-size:0.78rem;color:var(--text-2);margin-bottom:6px;font-weight:600;text-transform:uppercase;'>{translate("class_distribution")}</div>
  {bars}
</div>
""",
        unsafe_allow_html=True,
    )
    if result.get("stage_breakdown"):
        st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
        with st.expander(translate("stage_scores"), expanded=False):
            st.json(result["stage_breakdown"])
