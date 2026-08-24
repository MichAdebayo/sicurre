"""Data lineage and dataset evidence page for the local POC."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import streamlit as st

from poc.presentation.formatting import format_number

ROOT_DIR = Path(__file__).resolve().parents[3]
FROZEN_METADATA_PATH = (
    ROOT_DIR / "data" / "final" / "provenance" / "current_frozen" / "metadata.json"
)
SOURCE_FAMILY_COLORS = {
    "api": "#2E6BB5",
    "file": "#0F766E",
    "database": "#7C3AED",
    "bigdata": "#B45309",
    "scraping": "#BE123C",
    "other": "#64748B",
}


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


def _source_family(source: str, source_type: str = "") -> str:
    """Map persisted or frozen source names to certification acquisition families."""
    normalized = source.lower().replace("_", "-")
    normalized_type = source_type.lower().replace("_", "-")
    if "common-crawl" in normalized:
        return "bigdata"
    if normalized.startswith("sap-labs") or "certfr" in normalized or "sekoia" in normalized:
        return "scraping"
    if normalized.startswith("kaggle"):
        return "file"
    if normalized.startswith("database/") or normalized.startswith("synthetic-generated"):
        return "database"
    type_aliases = {
        "api": "api",
        "file": "file",
        "database": "database",
        "db": "database",
        "bigdata": "bigdata",
        "big-data": "bigdata",
        "scraping": "scraping",
    }
    return type_aliases.get(normalized_type, "other")


def _load_frozen_source_distribution(
    metadata_path: Path = FROZEN_METADATA_PATH,
) -> dict[str, int]:
    """Read immutable V1 source totals without claiming per-record lineage."""
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    distribution = payload.get("source_distribution", {})
    if not isinstance(distribution, dict):
        return {}
    return {
        str(source): int(count)
        for source, count in distribution.items()
        if isinstance(count, int) and count > 0
    }


def _source_family_rows(
    sources: list[dict[str, Any]], frozen_distribution: dict[str, int]
) -> list[dict[str, Any]]:
    """Combine recovered V1 totals with real post-V1 source lineage."""
    totals: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    has_reconstructed_base = any(
        str(row.get("name", "")).startswith("reconstructed/current_frozen/") for row in sources
    )
    if has_reconstructed_base:
        for source, count in frozen_distribution.items():
            family = _source_family(source)
            totals[family] += count
            provider_counts[family] += 1

    for row in sources:
        source = str(row.get("name", ""))
        count = int(row.get("total_records") or 0)
        if count <= 0 or source.startswith("reconstructed/current_frozen/"):
            continue
        family = _source_family(source, str(row.get("source_type") or ""))
        totals[family] += count
        provider_counts[family] += 1

    return [
        {"family": family, "count": count, "provider_count": provider_counts[family]}
        for family, count in totals.most_common()
    ]


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
    frozen_distribution = _load_frozen_source_distribution()
    chart_rows = _source_family_rows(sources, frozen_distribution)
    for row in chart_rows:
        row["family_label"] = translate(f"source_family_{row['family']}")
    if chart_rows:
        st.markdown(f"#### {translate('source_breakdown')}")
        if any(str(row["name"]).startswith("reconstructed/") for row in sources):
            st.caption(translate("reconstructed_lineage_note"))
        present_families = {str(row["family"]) for row in chart_rows}
        family_order = [family for family in SOURCE_FAMILY_COLORS if family in present_families]
        family_labels = [translate(f"source_family_{family}") for family in family_order]
        specification = {
            "height": 220,
            "mark": {
                "type": "bar",
                "cornerRadiusTopRight": 3,
                "cornerRadiusBottomRight": 3,
            },
            "encoding": {
                "y": {
                    "field": "family_label",
                    "type": "nominal",
                    "sort": "-x",
                    "axis": {"title": None, "labelFontSize": 13, "labelOverlap": False},
                },
                "x": {
                    "field": "count",
                    "type": "quantitative",
                    "axis": {"title": None, "grid": False, "labelFontSize": 12},
                },
                "color": {
                    "field": "family_label",
                    "type": "nominal",
                    "legend": {"title": None, "orient": "bottom", "columns": 3},
                    "scale": {
                        "domain": family_labels,
                        "range": [SOURCE_FAMILY_COLORS[family] for family in family_order],
                    },
                },
                "tooltip": [
                    {
                        "field": "family_label",
                        "type": "nominal",
                        "title": translate("source_method"),
                    },
                    {"field": "count", "type": "quantitative", "title": translate("records")},
                    {
                        "field": "provider_count",
                        "type": "quantitative",
                        "title": translate("source_count"),
                    },
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
            f"{_source_label(str(row.get('name', '')), translate)}</span>"
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
    latest_dataset = evidence.query(
        """
        SELECT item_count
        FROM data_dataset
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    latest_item_count = int(latest_dataset[0]["item_count"]) if latest_dataset else 0
    columns = st.columns(4)
    _metric(columns[0], translate("total_raw"), evidence.count("data_raw_record"))
    _metric(
        columns[1],
        translate("total_normalized"),
        evidence.count("data_normalized_message"),
    )
    _metric(
        columns[2],
        translate("total_dataset_items"),
        latest_item_count,
    )
    _metric(columns[3], translate("dataset_versions"), evidence.count("data_dataset"))
    st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)
    _render_sources(evidence, translate)
    _render_versions(evidence, translate)
