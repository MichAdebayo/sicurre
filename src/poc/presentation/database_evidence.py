"""Read-only SQLite persistence evidence for POC administrators."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import streamlit as st

from poc.presentation.formatting import format_number


class DatabaseEvidence(Protocol):
    """Bounded database evidence exposed to the presentation."""

    def count(self, table_name: str) -> int: ...

    def query(self, query: str) -> list[dict[str, Any]]: ...

    def integrity_status(self) -> tuple[bool, int]: ...


def render_database_evidence(
    evidence: DatabaseEvidence,
    translate: Callable[[str], str],
) -> None:
    """Render safe persistence, lineage, and integrity evidence."""
    st.title(translate("database_evidence_title"))
    st.caption(translate("database_evidence_subtitle"))

    integrity_ok, foreign_key_errors = evidence.integrity_status()
    status_columns = st.columns(2)
    status_columns[0].metric(
        translate("database_integrity"),
        translate("status_valid") if integrity_ok else translate("status_invalid"),
    )
    status_columns[1].metric(translate("foreign_key_errors"), foreign_key_errors)

    st.markdown(f"#### {translate('lineage_counts')}")
    count_columns = st.columns(4)
    tables = (
        ("data_source_system", "source_systems"),
        ("data_raw_record", "total_raw"),
        ("data_normalized_message", "total_normalized"),
        ("data_dataset", "dataset_versions"),
    )
    for column, (table_name, label_key) in zip(count_columns, tables, strict=True):
        column.metric(translate(label_key), format_number(evidence.count(table_name)))

    st.markdown(f"#### {translate('dataset_versions')}")
    versions = evidence.query(
        """
        SELECT version_tag, item_count, status, created_at
        FROM data_dataset
        ORDER BY created_at DESC
        LIMIT 12
        """
    )
    if versions:
        st.dataframe(
            [
                {
                    translate("dataset_version"): row["version_tag"],
                    translate("total_dataset_items"): row["item_count"],
                    translate("status"): row["status"],
                    translate("created_at"): row["created_at"],
                }
                for row in versions
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(translate("no_datasets"))

    st.markdown(f"#### {translate('recent_ingestion')}")
    runs = evidence.query(
        """
        SELECT ss.name AS source, ir.status, ir.raw_record_count, ir.finished_at
        FROM data_ingestion_run ir
        JOIN data_source_system ss ON ss.id = ir.source_system_id
        ORDER BY ir.finished_at DESC
        LIMIT 12
        """
    )
    if runs:
        st.dataframe(
            [
                {
                    translate("source"): row["source"],
                    translate("status"): row["status"],
                    translate("records"): row["raw_record_count"],
                    translate("last_run"): row["finished_at"],
                }
                for row in runs
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(translate("no_ingestion"))

    st.caption(translate("database_evidence_privacy"))
