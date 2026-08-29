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
DeleteEvent = Callable[[str, str], None]
Period = Literal["all", "today", "week"]
THREAT_PAGE_SIZE = 10


def _request_confirmation(action: str, event_id: str, surface: str) -> None:
    """Persist one pending remediation action until the user confirms it."""
    st.session_state["pending_remediation"] = {
        "action": action,
        "event_id": event_id,
        "surface": surface,
    }


def _dismiss_confirmation() -> None:
    """Clear a pending action when Streamlit's native close control is used."""
    st.session_state.pop("pending_remediation", None)


def clear_stale_confirmation(current_page: str) -> None:
    """Discard a pending action after navigation leaves its owning page."""
    pending = st.session_state.get("pending_remediation")
    if pending and pending.get("surface") != current_page:
        st.session_state.pop("pending_remediation", None)


def _render_confirmation(
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
    delete_event: DeleteEvent,
) -> None:
    """Render the single confirmation gate for destructive-looking actions."""
    pending = st.session_state.get("pending_remediation")
    if not pending:
        return

    @st.dialog(translate("confirmation_title"), on_dismiss=_dismiss_confirmation)
    def confirmation_dialog() -> None:
        action = str(pending["action"])
        st.write(translate(f"confirmation_{action}"))
        cancel, confirm = st.columns(2)
        if cancel.button(translate("cancel"), use_container_width=True):
            st.session_state.pop("pending_remediation", None)
            st.rerun()
        if confirm.button(
            translate("confirm"),
            type="primary",
            use_container_width=True,
        ):
            event_id = str(pending["event_id"])
            if action == "report_phishing":
                reclassify(event_id, "phishing", user_email)
            elif action == "restore_safe":
                reclassify(event_id, "safe", user_email)
            elif action == "delete":
                delete_event(event_id, user_email)
            st.session_state.pop("pending_remediation", None)
            st.session_state["remediation_completed"] = action
            st.rerun()

    confirmation_dialog()


def _render_completed_notice(translate: Translator) -> None:
    """Show one concise completion notice after a confirmed action."""
    action = st.session_state.pop("remediation_completed", None)
    if action:
        st.toast(translate(f"remediation_{action}_done"))


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


def paginate_threats(
    threats: list[dict[str, Any]], page: int, page_size: int = THREAT_PAGE_SIZE
) -> tuple[list[dict[str, Any]], int, int]:
    """Return one bounded threat page, its normalized index, and total pages."""
    total_pages = max(1, (len(threats) + page_size - 1) // page_size)
    normalized_page = min(max(page, 1), total_pages)
    start = (normalized_page - 1) * page_size
    return threats[start : start + page_size], normalized_page, total_pages


def _render_delivered_card(
    event: dict[str, Any],
    tab_key: str,
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
    delete_event: DeleteEvent,
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
    with st.container(
        key=f"smail_actions_{tab_key}_{event['id']}",
        horizontal=True,
        horizontal_alignment="left",
        vertical_alignment="center",
        gap="small",
    ):
        if st.button(translate("flag_false_negative"), key=f"fn_{tab_key}_{event['id']}"):
            _request_confirmation("report_phishing", str(event["id"]), "nav_smail")
            st.rerun()
        if st.button(translate("delete_event"), key=f"delete_{tab_key}_{event['id']}"):
            _request_confirmation("delete", str(event["id"]), "nav_smail")
            st.rerun()


def render_smail(
    events: list[dict[str, Any]],
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
    delete_event: DeleteEvent,
) -> None:
    """Render delivered mail and the false-negative feedback action."""
    _render_completed_notice(translate)
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
            _render_delivered_card(event, "inbox", user_email, translate, reclassify, delete_event)
    with spam_tab:
        if not spam:
            st.info(translate("smail_empty_spam"))
        for event in spam:
            _render_delivered_card(event, "spam", user_email, translate, reclassify, delete_event)
    _render_confirmation(user_email, translate, reclassify, delete_event)


def render_threat_log(
    events: list[dict[str, Any]],
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
    delete_event: DeleteEvent,
) -> None:
    """Render blocked threats and the false-positive remediation action."""
    _render_completed_notice(translate)
    st.title(translate("threat_title"))
    st.caption(translate("threat_reclassify_subtitle"))
    filter_column, _ = st.columns([1, 3])
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
    if st.session_state.get("threat_log_period") != selected_period:
        st.session_state["threat_log_period"] = selected_period
        st.session_state["threat_log_page"] = 1
    threats = filter_threats(events, selected_period)
    if not threats:
        st.info(translate("no_events"))
        return

    requested_page = int(st.session_state.get("threat_log_page", 1))
    visible_threats, current_page, total_pages = paginate_threats(
        threats,
        requested_page,
    )
    st.session_state["threat_log_page"] = current_page
    for event in visible_threats:
        _render_threat_card(
            event,
            user_email,
            translate,
            reclassify,
            delete_event,
        )
    if total_pages > 1:
        previous, page_status, following = st.columns([1, 2, 1])
        if previous.button(
            translate("pagination_previous"),
            disabled=current_page == 1,
            use_container_width=True,
        ):
            st.session_state["threat_log_page"] = current_page - 1
            st.rerun()
        page_status.markdown(
            f"<p class='pagination-status'>{translate('pagination_status').format(page=current_page, total=total_pages)}</p>",
            unsafe_allow_html=True,
        )
        if following.button(
            translate("pagination_next"),
            disabled=current_page == total_pages,
            use_container_width=True,
        ):
            st.session_state["threat_log_page"] = current_page + 1
            st.rerun()
    _render_confirmation(user_email, translate, reclassify, delete_event)


def _render_threat_card(
    event: dict[str, Any],
    user_email: str,
    translate: Translator,
    reclassify: Reclassify,
    delete_event: DeleteEvent,
) -> None:
    timestamp = event["created_at"].replace("T", " ")[:16]
    score = float(event.get("composite_score") or 0.0) * 100.0
    correction = ""
    if event.get("override_verdict") == "phishing":
        correction = (
            f" &nbsp;<span class='badge badge-human-report'>"
            f"{translate('reported_phishing_label')}</span>"
        )
    elif event.get("override_verdict"):
        correction = (
            f" &nbsp;<span class='badge badge-safe'>{translate('restored_safe_label')}</span>"
        )
    snippet = remove_links(safe_text(event.get("snippet") or "", 200))
    st.markdown(
        "<div class='threat-card'>"
        f"<div class='tc-subject'>{safe_text(event['subject'], 90)}</div>"
        f"<div class='tc-meta'>{safe_text(event['sender'], 70)} &middot; "
        f"{timestamp} &middot; {translate('initial_model_risk')} {score:.0f} %"
        f"{correction}</div></div>",
        unsafe_allow_html=True,
    )
    with st.expander(translate("expand_body"), expanded=False):
        st.markdown(
            "<div class='threat-expander-content' style='font-size:0.9rem;margin:0;'>"
            f"<p style='margin:0!important;'>{snippet}</p></div>",
            unsafe_allow_html=True,
        )
        with st.container(
            key=f"threat_actions_{event['id']}",
            horizontal=True,
            horizontal_alignment="left",
            vertical_alignment="center",
            gap="small",
        ):
            if st.button(translate("reclassify_safe"), key=f"fp_{event['id']}"):
                _request_confirmation("restore_safe", str(event["id"]), "nav_threat_log")
                st.rerun()
            if st.button(translate("delete_event"), key=f"delete_threat_{event['id']}"):
                _request_confirmation("delete", str(event["id"]), "nav_threat_log")
                st.rerun()
