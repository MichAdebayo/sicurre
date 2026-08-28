"""Data lineage and dataset evidence page for the local POC."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any, Protocol

import streamlit as st

from poc.presentation.formatting import format_number
from poc.presentation.table import render_evidence_table

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
SOURCE_STAGE_COLORS = {
    "raw": "#2E6BB5",
    "normalized": "#0F766E",
    "dataset": "#B45309",
}
SOURCE_STAGES = ("raw", "normalized", "dataset")


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


def _render_incremental_run(evidence: DataEvidence, translate: Callable[[str], str]) -> None:
    """Show baseline initialization and later collection runs at comparable grain."""
    runs = evidence.query(
        """
        SELECT ir.id, ss.name, ir.status, ir.trigger_mode, ir.log_message,
               ir.raw_object_count, ir.raw_record_count, ir.started_at, ir.finished_at,
               COUNT(DISTINCT nm.id) AS normalized_count,
               COUNT(DISTINCT di.normalized_message_id) AS dataset_item_count,
               MAX(ro.source_metadata) AS source_metadata
        FROM data_ingestion_run ir
        JOIN data_source_system ss ON ss.id = ir.source_system_id
        LEFT JOIN data_raw_object ro ON ro.ingestion_run_id = ir.id
        LEFT JOIN data_raw_record rr ON rr.raw_object_id = ro.id
        LEFT JOIN data_normalized_message nm ON nm.raw_record_id = rr.id
        LEFT JOIN data_dataset_item di
          ON di.normalized_message_id = nm.id
         AND di.dataset_id = (
             SELECT id FROM data_dataset ORDER BY created_at DESC LIMIT 1
         )
        GROUP BY ir.id, ss.name
        ORDER BY datetime(ir.finished_at) DESC
        LIMIT 20
        """
    )
    st.markdown(f"#### {translate('incremental_run_title')}")
    if not runs:
        st.info(translate("no_incremental_runs"))
        return

    display_runs = _aggregate_initialization_runs(runs, translate)
    run_index = {str(row["id"]): row for row in display_runs}
    preferred_id = st.session_state.pop("pending_dataset_run_id", None)
    current_id = st.session_state.get("dataset_run_selection")
    if preferred_id in run_index:
        st.session_state["dataset_run_selection"] = preferred_id
    elif current_id not in run_index:
        st.session_state["dataset_run_selection"] = next(iter(run_index))
    selected_id = st.selectbox(
        translate("incremental_run_select"),
        list(run_index),
        format_func=lambda run_id: _run_label(run_index[run_id], translate),
        key="dataset_run_selection",
    )
    selected = run_index[selected_id]
    st.caption(
        translate(
            "run_scope_initialization"
            if str(selected.get("trigger_mode") or "").lower()
            in {"poc_replay", "reconstructed_frozen_dataset"}
            else "run_scope_incremental"
        )
    )
    fetched_count, skipped_count = _run_fetch_counts(selected)
    values = (
        (translate("run_fetched"), fetched_count),
        (translate("run_raw_objects"), int(selected.get("raw_object_count") or 0)),
        (translate("run_raw_records"), int(selected.get("raw_record_count") or 0)),
        (translate("run_deduplicated"), skipped_count),
        (translate("run_normalized"), int(selected.get("normalized_count") or 0)),
        (translate("run_dataset_items"), int(selected.get("dataset_item_count") or 0)),
    )
    cells = "".join(
        "<div class='evidence-step'>"
        f"<span>{escape(label)}</span><strong>{format_number(value)}</strong></div>"
        for label, value in values
    )
    st.markdown(f"<div class='evidence-funnel'>{cells}</div>", unsafe_allow_html=True)

    raw_count = int(selected.get("raw_record_count") or 0)
    normalized_count = int(selected.get("normalized_count") or 0)
    if raw_count > 0 and normalized_count == 0:
        st.info(translate("incremental_run_reference_only"))


def _aggregate_initialization_runs(
    runs: list[dict[str, Any]],
    translate: Callable[[str], str],
) -> list[dict[str, Any]]:
    """Collapse reconstructed V1 lineage into one demonstrable initialization."""
    baseline = [
        row
        for row in runs
        if str(row.get("name") or "").startswith("reconstructed/")
        or str(row.get("trigger_mode") or "").lower() == "poc_replay"
    ]
    incremental = [row for row in runs if row not in baseline]
    if not baseline:
        return incremental
    aggregate: dict[str, Any] = {
        "id": "base-initialization",
        "name": translate("source_baseline_v1"),
        "status": "completed",
        "trigger_mode": "reconstructed_frozen_dataset",
        "raw_object_count": sum(int(row.get("raw_object_count") or 0) for row in baseline),
        "raw_record_count": sum(int(row.get("raw_record_count") or 0) for row in baseline),
        "normalized_count": sum(int(row.get("normalized_count") or 0) for row in baseline),
        "dataset_item_count": sum(int(row.get("dataset_item_count") or 0) for row in baseline),
        "started_at": min(str(row.get("started_at") or "") for row in baseline),
        "finished_at": max(str(row.get("finished_at") or "") for row in baseline),
    }
    return [*incremental, aggregate]


def _run_fetch_counts(row: dict[str, Any]) -> tuple[int, int]:
    """Return fetched and deduplicated counts from bounded source metadata."""
    metadata = row.get("source_metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    raw_count = int(row.get("raw_record_count") or 0)
    if not isinstance(metadata, dict):
        metadata = {}
    if not metadata:
        fetched_match = re.search(
            r"returned\s+([\d\s,]+)\s+IOC", str(row.get("log_message") or ""), re.IGNORECASE
        )
        if fetched_match:
            fetched = int(fetched_match.group(1).replace(" ", "").replace(",", ""))
            return fetched, max(0, fetched - raw_count)
        return raw_count, 0
    fetched = int(
        metadata.get("total_ioc_count")
        or metadata.get("feed_entry_count")
        or raw_count
    )
    persisted = int(metadata.get("new_ioc_count") or metadata.get("new_entry_count") or raw_count)
    return fetched, max(0, fetched - persisted)


def _run_label(row: dict[str, Any], translate: Callable[[str], str]) -> str:
    """Build a concise selector label for one ingestion run."""
    finished_at = _local_run_time(row.get("finished_at") or row.get("started_at"))
    name = _source_label(str(row.get("name") or "-"), translate)
    operation = _run_operation_label(row, translate)
    records = format_number(int(row.get("raw_record_count") or 0))
    return f"{finished_at} · {operation} · {name} · {records} {translate('records')}"


def _run_operation_label(row: dict[str, Any], translate: Callable[[str], str]) -> str:
    """Describe a run by its demonstration operation rather than its storage trigger."""
    trigger_mode = str(row.get("trigger_mode") or "").lower()
    if trigger_mode in {"poc_replay", "reconstructed_frozen_dataset"}:
        return translate("run_operation_initialization")
    if trigger_mode == "scheduled":
        return translate("run_operation_incremental")
    return translate("run_operation_manual")


def _local_run_time(value: object) -> str:
    """Format a persisted UTC timestamp in the POC host's local timezone."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return "-"
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return raw_value[:16].replace("T", " ")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def _source_label(source: str, translate: Callable[[str], str]) -> str:
    """Return a concise label while retaining canonical lineage separately."""
    if "phishtank" in source.lower():
        return translate("source_provider_phishtank")
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


def _source_provider(source: str) -> str:
    """Group detailed lineage into concise, truthful provider bars."""
    normalized = source.lower().replace("_", "-")
    if normalized.startswith("kaggle"):
        return "kaggle"
    if normalized.startswith("database/faker"):
        return "faker"
    if "adapted" in normalized:
        return "adapted"
    if "common-crawl" in normalized:
        return "common_crawl"
    if normalized.startswith("sap-labs"):
        return "sap_labs"
    if "phishtank" in normalized:
        return "phishtank"
    if "sekoia" in normalized:
        return "sekoia"
    return "other"


def _training_provider_rows(frozen_distribution: dict[str, int]) -> list[dict[str, Any]]:
    """Build provider totals for the active training corpus only."""
    totals: Counter[tuple[str, str]] = Counter()
    for source, count in frozen_distribution.items():
        totals[(_source_provider(source), _source_family(source))] += count

    return [
        {"provider": provider, "family": family, "count": count}
        for (provider, family), count in totals.most_common()
    ]


def _reference_provider_rows(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build provider totals for reference-only threat indicators."""
    rows = []
    for source in sources:
        count = int(source.get("reference_records") or 0)
        name = str(source.get("name") or "")
        if count <= 0:
            continue
        rows.append(
            {
                "provider": _source_provider(name),
                "family": _source_family(name, str(source.get("source_type") or "")),
                "count": count,
            }
        )
    return rows


def _source_stage_rows(
    frozen_distribution: dict[str, int],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build one synchronized raw-to-dataset projection for every provider."""
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    baseline_last_run = max(
        (
            str(source.get("last_run"))
            for source in sources
            if str(source.get("name") or "").startswith("reconstructed/current_frozen/")
            and source.get("last_run")
        ),
        default=None,
    )

    def provider_totals(provider: str, family: str) -> dict[str, Any]:
        return totals.setdefault(
            (provider, family),
            {
                "provider": provider,
                "family": family,
                "raw": 0,
                "normalized": 0,
                "dataset": 0,
                "roles": set(),
                "last_run": None,
            },
        )

    for source, count in frozen_distribution.items():
        row = provider_totals(_source_provider(source), _source_family(source))
        for stage in SOURCE_STAGES:
            row[stage] += count
        row["roles"].add("training")
        row["last_run"] = baseline_last_run

    for source in sources:
        name = str(source.get("name") or "")
        if name.startswith("reconstructed/current_frozen/"):
            continue
        provider = _source_provider(name)
        family = _source_family(name, str(source.get("source_type") or ""))
        row = provider_totals(provider, family)
        raw_count = int(source.get("total_records") or 0)
        reference_count = int(source.get("reference_records") or 0)
        trainable_raw_count = max(0, raw_count - reference_count)
        row["raw"] += raw_count
        row["normalized"] += int(source.get("normalized_records") or 0)
        row["dataset"] += int(source.get("dataset_records") or 0)
        if trainable_raw_count:
            row["roles"].add("training")
        if reference_count:
            row["roles"].add("reference")
        if source.get("last_run"):
            row["last_run"] = source["last_run"]

    rows: list[dict[str, Any]] = []
    for row in totals.values():
        role = "mixed" if len(row["roles"]) > 1 else next(iter(row["roles"]), "training")
        for stage in SOURCE_STAGES:
            rows.append(
                {
                    "provider": row["provider"],
                    "family": row["family"],
                    "role": role,
                    "stage": stage,
                    "count": int(row[stage]),
                    "raw_total": int(row["raw"]),
                    "last_run": row["last_run"],
                }
            )
    return rows


def _render_source_stage_chart(
    rows: list[dict[str, Any]], translate: Callable[[str], str]
) -> None:
    """Render grouped pipeline-stage bars for each persisted source provider."""
    if not rows:
        return
    chart_rows = [dict(row) for row in rows]
    stage_domain = [translate(f"source_stage_{stage}") for stage in SOURCE_STAGES]
    for row in chart_rows:
        family_label = translate(f"source_family_{row['family']}")
        provider_label = translate(f"source_provider_{row['provider']}")
        row["family_label"] = family_label
        row["provider_label"] = f"{provider_label} · {family_label}"
        row["role_label"] = translate(f"source_role_{row['role']}")
        row["stage_label"] = translate(f"source_stage_{row['stage']}")
        row["last_run_label"] = _local_run_time(row.get("last_run"))

    shared_encoding = {
        "y": {
            "field": "provider_label",
            "type": "nominal",
            "sort": {"field": "raw_total", "order": "descending"},
            "axis": {"title": None, "labelFontSize": 12, "labelLimit": 250},
        },
        "yOffset": {"field": "stage_label", "sort": stage_domain},
        "x": {
            "field": "count",
            "type": "quantitative",
            "axis": {
                "title": translate("records"),
                "grid": False,
                "tickCount": 6,
                "labelFontSize": 11,
            },
        },
    }
    tooltip = [
        {"field": "provider_label", "type": "nominal", "title": translate("source")},
        {"field": "role_label", "type": "nominal", "title": translate("source_role")},
        {"field": "stage_label", "type": "nominal", "title": translate("pipeline_stage")},
        {"field": "count", "type": "quantitative", "title": translate("records")},
        {
            "field": "last_run_label",
            "type": "nominal",
            "title": translate("last_local_update"),
        },
    ]
    specification = {
        "height": max(320, len({row["provider_label"] for row in chart_rows}) * 74),
        "mark": {
            "type": "bar",
            "cornerRadiusTopRight": 3,
            "cornerRadiusBottomRight": 3,
        },
        "encoding": {
            **shared_encoding,
            "color": {
                "field": "stage_label",
                "type": "nominal",
                "legend": {"title": None, "orient": "bottom", "columns": 3},
                "scale": {
                    "domain": stage_domain,
                    "range": [SOURCE_STAGE_COLORS[stage] for stage in SOURCE_STAGES],
                },
            },
            "tooltip": tooltip,
        },
        "config": {
            "background": "transparent",
            "view": {"stroke": "transparent"},
        },
    }
    st.vega_lite_chart(chart_rows, specification, width="stretch")


def _render_sources(evidence: DataEvidence, translate: Callable[[str], str]) -> None:
    if not (
        evidence.table_exists("data_source_system")
        and evidence.table_exists("data_ingestion_run")
        and evidence.table_exists("data_raw_record")
        and evidence.table_exists("data_normalized_message")
        and evidence.table_exists("data_dataset")
        and evidence.table_exists("data_dataset_item")
    ):
        st.info(translate("run_pipeline_hint"))
        return
    sources = evidence.query(
        """
        SELECT ss.name, ss.source_type,
               COUNT(DISTINCT rr.id) AS total_records,
               COUNT(DISTINCT CASE
                   WHEN rr.rejection_reason = 'ioc_reference_only_not_email_training_text'
                   THEN rr.id END) AS reference_records,
               COUNT(DISTINCT nm.id) AS normalized_records,
               COUNT(DISTINCT CASE
                   WHEN di.dataset_id = (
                       SELECT id FROM data_dataset ORDER BY created_at DESC LIMIT 1
                   ) THEN di.normalized_message_id END) AS dataset_records,
               (SELECT MAX(ir.finished_at)
                FROM data_ingestion_run ir
                WHERE ir.source_system_id = ss.id) AS last_run
        FROM data_source_system ss
        LEFT JOIN data_raw_record rr ON rr.source_system_id = ss.id
        LEFT JOIN data_normalized_message nm ON nm.raw_record_id = rr.id
        LEFT JOIN data_dataset_item di ON di.normalized_message_id = nm.id
        GROUP BY ss.id
        ORDER BY total_records DESC
        LIMIT 30
        """
    )
    frozen_distribution = _load_frozen_source_distribution()
    if frozen_distribution:
        st.caption(translate("reconstructed_lineage_note"))
    stage_rows = _source_stage_rows(frozen_distribution, sources)
    st.markdown(f"#### {translate('source_stage_chart_title')}")
    st.caption(translate("source_stage_chart_help"))
    _render_source_stage_chart(stage_rows, translate)

    if stage_rows:
        grouped_rows: dict[tuple[str, str], dict[str, Any]] = {}
        for row in stage_rows:
            key = (str(row["provider"]), str(row["family"]))
            grouped = grouped_rows.setdefault(
                key,
                {
                    translate("source"): translate(f"source_provider_{row['provider']}"),
                    translate("source_method"): translate(f"source_family_{row['family']}"),
                    translate("source_role"): translate(f"source_role_{row['role']}"),
                },
            )
            grouped[translate(f"source_stage_{row['stage']}")] = int(row["count"])
        with st.expander(translate("source_provider_details")):
            columns = (
                translate("source"),
                translate("source_method"),
                translate("source_role"),
                *(translate(f"source_stage_{stage}") for stage in SOURCE_STAGES),
            )
            render_evidence_table(
                list(grouped_rows.values()),
                columns,
                caption=translate("source_provider_table_caption"),
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
            f"<strong>{row.get('version_tag', '-')}</strong>"
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
    raw_total = evidence.count("data_raw_record")
    normalized_total = evidence.count("data_normalized_message")
    reference_rows = evidence.query(
        """
        SELECT COUNT(*) AS count
        FROM data_raw_record
        WHERE rejection_reason = 'ioc_reference_only_not_email_training_text'
        """
    )
    reference_total = int(reference_rows[0]["count"]) if reference_rows else 0
    st.markdown(f"#### {translate('dataset_current_state')}")
    columns = st.columns(3)
    _metric(columns[0], translate("raw_record_total"), raw_total)
    _metric(columns[1], translate("training_corpus_items"), normalized_total)
    _metric(
        columns[2],
        translate("total_dataset_items"),
        latest_item_count,
    )
    st.caption(
        translate("dataset_scope_summary").format(
            reference_count=format_number(reference_total)
        )
    )
    st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)
    _render_incremental_run(evidence, translate)
    _render_sources(evidence, translate)
    _render_versions(evidence, translate)
