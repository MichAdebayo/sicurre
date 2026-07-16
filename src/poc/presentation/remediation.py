"""Inbox and threat-remediation presentation for the local POC."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import streamlit as st

from poc.presentation.formatting import (
    effective_label,
    effective_verdict,
    remove_links,
    safe_text,
)

Translator = Callable[[str], str]
Reclassify = Callable[[str, str, str], None]
Period = Literal["all", "today", "week"]


def partition_delivered_events(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition delivered demonstration emails into inbox and spam views."""
    delivered = [
        event
        for event in events
        if effective_verdict(event) == "safe"
        and event.get("context") in {"playground", "manual", "smail"}
    ]
    spam = [event for event in delivered if effective_label(event) == "spam"]
    inbox = [event for event in delivered if effective_label(event) != "spam"]
    return inbox, spam


def filter_threats(
    events: list[dict[str, Any]], period: Period, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Filter effective phishing events over a bounded demonstration period."""
    threats = [event for event in events if effective_verdict(event) == "phishing"]
    if period == "all":
        return threats
    current_time = now or datetime.now(UTC)
    cutoff = current_time - timedelta(days=1 if period == "today" else 7)
    return [event for event in threats if event["created_at"] >= cutoff.isoformat()]


def _render_delivered_card(
    event: dict[str, Any],
    tab_key: str,
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
) -> None:
    timestamp = event["created_at"].replace("T", " ")[:16]
    correction = (
        f"<span style='font-size:0.74rem;color:var(--text-muted);'> "
        f"({translate('corrected_label')})</span>"
        if event.get("override_verdict")
        else ""
    )
    snippet = remove_links(safe_text(event.get("snippet") or "", 160))
    st.markdown(
        "<div class='email-card'>"
        f"<div class='ec-sender'>{safe_text(event['sender'], 70)} &middot; "
        f"{timestamp}{correction}</div>"
        f"<div class='ec-subject'>{safe_text(event['subject'], 80)}</div>"
        f"<div class='ec-snippet'>{snippet}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='semantic-btn-danger'>", unsafe_allow_html=True)
    if st.button(translate("flag_false_negative"), key=f"fn_{tab_key}_{event['id']}"):
        reclassify(str(event["id"]), "phishing", user_email)
        st.toast(translate("reclassified_done"), icon="✅")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_smail(
    events: list[dict[str, Any]],
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
) -> None:
    """Render delivered mail and the false-negative feedback action."""
    st.title(translate("smail_title"))
    st.caption(translate("smail_inbox_subtitle"))
    legitimate, spam = partition_delivered_events(events)
    inbox_tab, spam_tab = st.tabs(
        [
            f"{translate('smail_inbox_tab')} ({len(legitimate)})",
            f"{translate('smail_spam_tab')} ({len(spam)})",
        ]
    )
    with inbox_tab:
        if not legitimate:
            st.info(translate("smail_empty_inbox"))
        for event in legitimate:
            _render_delivered_card(event, "inbox", user_email, translate, reclassify)
    with spam_tab:
        if not spam:
            st.info(translate("smail_empty_spam"))
        for event in spam:
            _render_delivered_card(event, "spam", user_email, translate, reclassify)


def render_threat_log(
    events: list[dict[str, Any]],
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
) -> None:
    """Render blocked threats and the false-positive remediation action."""
    st.title(translate("threat_title"))
    st.caption(translate("threat_reclassify_subtitle"))
    filter_column, _, _ = st.columns([1, 2, 2])
    options: list[tuple[Period, str]] = [
        ("all", translate("period_all")),
        ("today", translate("period_today")),
        ("week", translate("period_week")),
    ]
    with filter_column:
        selected_label = st.selectbox(
            translate("filter_period"),
            [label for _, label in options],
            label_visibility="collapsed",
        )
    selected_period = next(key for key, label in options if label == selected_label)
    threats = filter_threats(events, selected_period)
    if not threats:
        st.info(translate("no_events"))
        return

    for event in threats[:80]:
        _render_threat_card(event, user_email, translate, reclassify)


def _render_threat_card(
    event: dict[str, Any],
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
) -> None:
    timestamp = event["created_at"].replace("T", " ")[:16]
    score = float(event.get("composite_score") or 0.0) * 100.0
    correction = ""
    if event.get("override_verdict") == "phishing":
        correction = (
            f" &nbsp;<span class='badge badge-phishing'>{translate('corrected_label')}</span>"
        )
    elif event.get("override_verdict"):
        correction = f" &nbsp;<span class='badge badge-safe'>{translate('corrected_label')}</span>"
    snippet = remove_links(safe_text(event.get("snippet") or "", 200))
    st.markdown(
        "<div class='threat-card'>"
        f"<div class='tc-subject'>{safe_text(event['subject'], 90)}</div>"
        f"<div class='tc-meta'>{safe_text(event['sender'], 70)} &middot; "
        f"{timestamp} &middot; {score:.0f} %{correction}</div></div>",
        unsafe_allow_html=True,
    )
    with st.expander(translate("expand_body"), expanded=False):
        st.markdown(
            "<div class='threat-expander-content' style='font-size:0.9rem;margin:0;'>"
            f"<p style='margin:0!important;'>{snippet}</p></div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='semantic-btn-safe'>", unsafe_allow_html=True)
        if st.button(translate("reclassify_safe"), key=f"fp_{event['id']}"):
            reclassify(str(event["id"]), "safe", user_email)
            st.toast(translate("reclassified_done"), icon="✅")
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
