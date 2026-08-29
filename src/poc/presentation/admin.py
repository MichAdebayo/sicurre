"""Administration overview for the local certification POC."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from html import escape
from typing import Any

import streamlit as st

from poc.admin_analytics import AdminSnapshot
from poc.presentation.formatting import format_number
from poc.presentation.table import render_evidence_table
from poc.runtime_preflight import RuntimeCheck

ReadinessState = tuple[str, str]


def _metric(column: Any, label: str, value: str) -> None:
    column.markdown(
        f"<div class='kpi'><div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(value)}</div></div>",
        unsafe_allow_html=True,
    )


def _render_classification_chart(
    snapshot: AdminSnapshot,
    translate: Callable[[str], str],
) -> None:
    totals = snapshot.classifications
    rows = [
        {"class": translate("class_legitimate"), "count": totals.legitimate},
        {"class": translate("class_spam"), "count": totals.spam},
        {"class": translate("class_phishing"), "count": totals.phishing},
    ]
    specification = {
        "height": 210,
        "mark": {"type": "bar", "cornerRadiusEnd": 4},
        "encoding": {
            "y": {"field": "class", "type": "nominal", "axis": {"title": None}},
            "x": {
                "field": "count",
                "type": "quantitative",
                "axis": {
                    "title": translate("admin_processed_messages"),
                    "format": ",d",
                    "tickMinStep": 1,
                    "grid": False,
                },
            },
            "color": {
                "field": "class",
                "type": "nominal",
                "legend": None,
                "scale": {
                    "domain": [row["class"] for row in rows],
                    "range": ["#047857", "#B45309", "#BE123C"],
                },
            },
            "tooltip": [
                {"field": "class", "type": "nominal", "title": translate("filter_class")},
                {
                    "field": "count",
                    "type": "quantitative",
                    "title": translate("admin_processed_messages"),
                    "format": ",d",
                },
            ],
        },
        "config": {"background": "transparent", "view": {"stroke": "transparent"}},
    }
    st.vega_lite_chart(rows, specification, width="stretch")


def _render_accounts(snapshot: AdminSnapshot, translate: Callable[[str], str]) -> None:
    rows = [
        {
            translate("admin_row_number"): position,
            translate("display_name"): account.display_name,
            translate("email"): account.email,
            translate("admin_role"): translate(f"admin_role_{account.role}"),
            translate("admin_activity"): format_number(account.event_count),
            translate("admin_last_login"): _display_time(account.last_login_at)
            or translate("admin_never"),
        }
        for position, account in enumerate(snapshot.accounts, start=1)
    ]
    columns = tuple(rows[0]) if rows else ()
    if rows:
        render_evidence_table(
            rows,
            columns,
            caption=translate("admin_accounts_caption"),
            wrapper_class="admin-accounts-table",
        )
    else:
        st.info(translate("admin_no_accounts"))


def _render_readiness(
    checks: Sequence[RuntimeCheck],
    inference_state: tuple[str, str],
    translate: Callable[[str], str],
) -> None:
    state, _ = inference_state
    rows: list[tuple[str, ReadinessState]] = [
        (translate("inference_status"), _inference_readiness(state, translate)),
        *[
            (translate(check.key), _check_readiness(check, translate))
            for check in checks
        ],
    ]
    body = "".join(
        "<tr>"
        f"<td>{escape(control)}</td>"
        "<td>"
        f"<span class='readiness-status readiness-{escape(status_kind)}'>"
        f"{escape(status_label)}</span>"
        "</td></tr>"
        for control, (status_kind, status_label) in rows
    )
    st.markdown(
        "<div class='evidence-table-scroll'>"
        "<table class='evidence-table readiness-table'>"
        f"<caption>{escape(translate('admin_readiness_caption'))}</caption>"
        "<thead><tr>"
        f"<th scope='col'>{escape(translate('admin_control'))}</th>"
        f"<th scope='col'>{escape(translate('status'))}</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    if state != "ready":
        st.warning(translate("admin_inference_attention"))


def _check_readiness(
    check: RuntimeCheck,
    translate: Callable[[str], str],
) -> ReadinessState:
    """Map a preflight check to text-backed semantic status."""
    if check.ready:
        return "ready", translate("preflight_ready")
    if check.blocking:
        return "blocking", translate("preflight_blocking")
    return "attention", translate("preflight_attention")


def _inference_readiness(
    state: str,
    translate: Callable[[str], str],
) -> ReadinessState:
    """Map the live inference probe to the shared readiness vocabulary."""
    if state == "ready":
        return "ready", translate("preflight_ready")
    if state in {"authentication_rejected", "contract_invalid"}:
        return "attention", translate("preflight_attention")
    return "blocking", translate("preflight_blocking")


def _ingestion_status(
    status: str | None,
    translate: Callable[[str], str],
) -> ReadinessState:
    """Normalize the latest ingestion status for the compact overview."""
    normalized = (status or "").strip().lower()
    if normalized in {"completed", "complete", "success", "succeeded"}:
        return "ready", translate("admin_ingestion_completed")
    if normalized in {"running", "in_progress", "pending", "started"}:
        return "attention", translate("admin_ingestion_running")
    if normalized in {"failed", "error"}:
        return "blocking", translate("admin_ingestion_failed")
    return "attention", translate("admin_unavailable")


def _render_data_summary(
    snapshot: AdminSnapshot,
    translate: Callable[[str], str],
) -> None:
    """Render overview-level data evidence without duplicating dataset details."""
    data = snapshot.data_platform
    version = data.dataset_version or translate("admin_unavailable")
    observed_at = _display_time(data.latest_ingestion_at) or translate("admin_unavailable")
    status_kind, status_label = _ingestion_status(
        data.latest_ingestion_status,
        translate,
    )
    st.markdown(
        "<div class='admin-data-summary'>"
        "<div class='admin-data-item'>"
        f"<div class='admin-data-label'>{escape(translate('admin_dataset_version'))}</div>"
        f"<div class='admin-data-value'>{escape(version)}</div>"
        f"<div class='admin-data-meta'>{escape(translate('admin_dataset_items'))}: "
        f"{escape(format_number(data.dataset_items))}</div></div>"
        "<div class='admin-data-item'>"
        f"<div class='admin-data-label'>{escape(translate('admin_latest_ingestion'))}</div>"
        f"<span class='readiness-status readiness-{escape(status_kind)}'>"
        f"{escape(status_label)}</span>"
        f"<div class='admin-data-meta'>{escape(observed_at)}</div></div></div>",
        unsafe_allow_html=True,
    )


def _render_section_heading(label: str) -> None:
    """Render every dashboard section with one shared spacing contract."""
    st.markdown(
        f"<h4 class='admin-section-heading'>{escape(label)}</h4>",
        unsafe_allow_html=True,
    )


def render_admin_overview(
    snapshot: AdminSnapshot,
    checks: Sequence[RuntimeCheck],
    inference_state: tuple[str, str],
    translate: Callable[[str], str],
) -> None:
    """Render content-free POC usage, data, and runtime administration evidence."""
    st.title(translate("admin_title"))
    st.caption(translate("admin_subtitle"))

    totals = snapshot.classifications
    metrics = st.columns(4)
    _metric(metrics[0], translate("admin_accounts"), format_number(len(snapshot.accounts)))
    _metric(metrics[1], translate("admin_processed_messages"), format_number(totals.total))
    _metric(metrics[2], translate("class_phishing"), format_number(totals.phishing))
    _metric(metrics[3], translate("admin_corrections"), format_number(totals.corrections))

    _render_section_heading(translate("class_distribution"))
    _render_classification_chart(snapshot, translate)

    _render_section_heading(translate("admin_accounts_title"))
    _render_accounts(snapshot, translate)

    _render_section_heading(translate("admin_data_state"))
    _render_data_summary(snapshot, translate)

    _render_section_heading(translate("preflight_title"))
    _render_readiness(checks, inference_state, translate)


def _display_time(value: str | None) -> str | None:
    """Format persisted UTC timestamps at a useful administrative precision."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:16].replace("T", " ")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
