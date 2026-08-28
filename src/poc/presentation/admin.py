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
                "axis": {"title": translate("admin_processed_messages"), "grid": False},
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
                },
            ],
        },
        "config": {"background": "transparent", "view": {"stroke": "transparent"}},
    }
    st.vega_lite_chart(rows, specification, width="stretch")


def _render_accounts(snapshot: AdminSnapshot, translate: Callable[[str], str]) -> None:
    rows = [
        {
            translate("display_name"): account.display_name,
            translate("email"): account.email,
            translate("admin_role"): translate(f"admin_role_{account.role}"),
            translate("admin_activity"): format_number(account.event_count),
            translate("admin_last_login"): _display_time(account.last_login_at)
            or translate("admin_never"),
        }
        for account in snapshot.accounts
    ]
    columns = tuple(rows[0]) if rows else ()
    if rows:
        render_evidence_table(rows, columns, caption=translate("admin_accounts_caption"))
    else:
        st.info(translate("admin_no_accounts"))


def _render_readiness(
    checks: Sequence[RuntimeCheck],
    inference_state: tuple[str, str],
    translate: Callable[[str], str],
) -> None:
    state, inference_text = inference_state
    rows = [
        {
            translate("admin_control"): translate("inference_status"),
            translate("status"): inference_text,
        },
        *[
            {
                translate("admin_control"): translate(check.key),
                translate("status"): translate(
                    "preflight_ready" if check.ready else "preflight_attention"
                ),
            }
            for check in checks
        ],
    ]
    render_evidence_table(rows, tuple(rows[0]), caption=translate("admin_readiness_caption"))
    if state != "ready":
        st.warning(translate("admin_inference_attention"))


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

    chart_column, account_column = st.columns([1, 1.45])
    with chart_column:
        st.markdown(f"#### {translate('class_distribution')}")
        _render_classification_chart(snapshot, translate)
    with account_column:
        st.markdown(f"#### {translate('admin_accounts_title')}")
        _render_accounts(snapshot, translate)

    st.markdown(f"#### {translate('admin_data_state')}")
    data = snapshot.data_platform
    data_metrics = st.columns(3)
    _metric(data_metrics[0], translate("raw_record_total"), format_number(data.raw_records))
    _metric(
        data_metrics[1],
        translate("training_corpus_items"),
        format_number(data.normalized_messages),
    )
    _metric(data_metrics[2], translate("total_dataset_items"), format_number(data.dataset_items))
    st.caption(
        translate("admin_data_caption").format(
            version=data.dataset_version or translate("admin_unavailable"),
            status=translate(f"admin_dataset_status_{data.dataset_status}")
            if data.dataset_status
            else translate("admin_unavailable"),
            latest=_display_time(data.latest_ingestion_at) or translate("admin_unavailable"),
        )
    )

    st.markdown(f"#### {translate('preflight_title')}")
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
