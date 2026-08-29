"""Accessible theme-aware tables for compact POC evidence."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import Any

import streamlit as st


def render_evidence_table(
    rows: Sequence[dict[str, Any]],
    columns: Sequence[str],
    *,
    caption: str,
    wrapper_class: str = "",
) -> None:
    """Render a semantic table that follows the active Sicurre theme."""
    wrapper_classes = "evidence-table-scroll"
    if wrapper_class:
        wrapper_classes = f"{wrapper_classes} {escape(wrapper_class)}"
    headers = "".join(f"<th scope='col'>{escape(column)}</th>" for column in columns)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(str(row.get(column, '-')))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    st.markdown(
        f"<div class='{wrapper_classes}'>"
        "<table class='evidence-table'>"
        f"<caption>{escape(caption)}</caption>"
        f"<thead><tr>{headers}</tr></thead><tbody>{body}</tbody>"
        "</table></div>",
        unsafe_allow_html=True,
    )
