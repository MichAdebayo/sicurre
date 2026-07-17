"""Data lineage and dataset evidence page for the local POC."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import streamlit as st

from poc.presentation.formatting import format_number


class DataEvidence(Protocol):
    """Read-only evidence required by the dataset presentation."""

    def table_exists(self, table_name: str) -> bool: ...

    def query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    def count(self, table_name: str) -> int: ...


def _metric(column: Any, label: str, value: int) -> None:
    column.markdown(
        f"<div class='kpi'><div class='label'>{label}</div>"
        f"<div class='value'>{format_number(value)}</div></div>",
        unsafe_allow_html=True,
    )


def _source_label(source: str, translate: Callable[[str], str]) -> str:
    """Return a concise label while retaining canonical lineage separately."""
    reconstruction_key = source.rsplit("/", maxsplit=1)[-1]
    if source.startswith("reconstructed/current_frozen/"):
        return translate(f"reconstructed_source_{reconstruction_key}")
    return source


def _render_sources(evidence: DataEvidence, translate: Callable[[str], str]) -> None:
    if not (
        evidence.table_exists("data_source_system")
        and evidence.table_exists("data_ingestion_run")
        and evidence.table_exists("data_raw_record")
    ):
        st.info(translate("run_pipeline_hint"))
        return
    sources = evidence.query(
        """
        SELECT ss.name, ss.source_type,
               COUNT(rr.id) AS total_records,
               (SELECT MAX(ir.finished_at)
                FROM data_ingestion_run ir
                WHERE ir.source_system_id = ss.id) AS last_run
        FROM data_source_system ss
        LEFT JOIN data_raw_record rr ON rr.source_system_id = ss.id
        GROUP BY ss.id
        ORDER BY total_records DESC
        LIMIT 30
        """
    )
    chart_rows = [
        {
            "source": row["name"],
            "source_label": _source_label(str(row["name"]), translate),
            "count": int(row.get("total_records") or 0),
            "type": str(row.get("source_type") or "other"),
        }
        for row in sources
        if int(row.get("total_records") or 0) > 0
    ]
    if chart_rows:
        st.markdown(f"#### {translate('source_breakdown')}")
        if any(str(row["source"]).startswith("reconstructed/") for row in chart_rows):
            st.caption(translate("reconstructed_lineage_note"))
        specification = {
            "mark": {
                "type": "bar",
                "cornerRadiusTopRight": 3,
                "cornerRadiusBottomRight": 3,
            },
            "encoding": {
                "y": {
                    "field": "source_label",
                    "type": "nominal",
                    "sort": "-x",
                    "axis": {"title": None, "labelFontSize": 13},
                },
                "x": {
                    "field": "count",
                    "type": "quantitative",
                    "axis": {"title": None, "grid": False, "labelFontSize": 12},
                },
                "color": {"value": "#4A90D9"},
                "tooltip": [
                    {"field": "source", "type": "nominal", "title": translate("source")},
                    {"field": "type", "type": "nominal", "title": translate("source_method")},
                    {"field": "count", "type": "quantitative", "title": translate("records")},
                ],
            },
            "config": {"background": "transparent", "view": {"stroke": "transparent"}},
        }
        st.vega_lite_chart(chart_rows, specification, width="stretch")

    st.markdown(f"#### {translate('recent_ingestion')}")
    runs = evidence.query(
        """
        SELECT ss.name, ir.status, ir.raw_record_count, ir.finished_at
        FROM data_ingestion_run ir
        JOIN data_source_system ss ON ss.id = ir.source_system_id
        WHERE ir.finished_at IS NOT NULL
        ORDER BY ir.finished_at DESC
        LIMIT 20
        """
    )
    if not runs:
        st.info(translate("no_ingestion"))
        return
    for row in runs:
        finished_at = str(row.get("finished_at") or "")[:16].replace("T", " ")
        count = int(row.get("raw_record_count") or 0)
        status = str(row.get("status") or "")
        badge_class = (
            "badge-ok" if status.lower() in {"success", "completed", "done"} else "badge-danger"
        )
        st.markdown(
            "<div class='card' style='padding:9px 12px;margin-bottom:4px;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<span style='font-size:0.9rem;font-weight:600;color:var(--text);'>"
            f"{row.get('name', '')}</span>"
            f"<span class='badge {badge_class}'>{status}</span></div>"
            f"<div style='font-size:0.78rem;color:var(--text-muted);'>"
            f"{format_number(count)} {translate('records')} &middot; {finished_at}</div></div>",
            unsafe_allow_html=True,
        )


def _render_versions(evidence: DataEvidence, translate: Callable[[str], str]) -> None:
    if not evidence.table_exists("data_dataset"):
        return
    versions = evidence.query(
        """
        SELECT version_tag, status, item_count, created_at
        FROM data_dataset
        ORDER BY created_at DESC
        LIMIT 24
        """
    )
    st.markdown(f"#### {translate('dataset_title')}")
    if not versions:
        st.info(translate("no_datasets"))
        return
    for row in versions:
        created_at = str(row.get("created_at") or "")[:16].replace("T", " ")
        item_count = int(row.get("item_count") or 0)
        st.markdown(
            "<div class='card'>"
            f"<strong>{row.get('version_tag', '—')}</strong>"
            "<span style='margin-left:12px;font-size:0.82rem;color:var(--text-2);'>"
            f"{format_number(item_count)} {translate('rows')} &middot; {created_at} "
            f"&middot; {row.get('status', '')}</span></div>",
            unsafe_allow_html=True,
        )


def render_datasets(evidence: DataEvidence, translate: Callable[[str], str]) -> None:
    """Render local record volumes, source lineage, runs, and dataset versions."""
    st.title(translate("data_platform_title"))
    st.caption(translate("data_platform_subtitle"))
    columns = st.columns(3)
    _metric(columns[0], translate("total_raw"), evidence.count("data_raw_record"))
    _metric(
        columns[1],
        translate("total_normalized"),
        evidence.count("data_normalized_message"),
    )
    _metric(
        columns[2],
        translate("total_dataset_items"),
        evidence.count("data_dataset_item"),
    )
    st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)
    _render_sources(evidence, translate)
    _render_versions(evidence, translate)
