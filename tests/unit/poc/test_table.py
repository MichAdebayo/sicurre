"""Tests for accessible POC evidence tables."""

from unittest.mock import patch

from poc.presentation.table import render_evidence_table


def test_evidence_table_is_semantic_and_escapes_values() -> None:
    with patch("poc.presentation.table.st.markdown") as markdown:
        render_evidence_table(
            [{"Source": "<script>", "Records": 3}],
            ("Source", "Records"),
            caption="Acquisition evidence",
        )

    rendered = markdown.call_args.args[0]
    assert "<table class='evidence-table'>" in rendered
    assert "<th scope='col'>Source</th>" in rendered
    assert "&lt;script&gt;" in rendered
    assert "<caption>Acquisition evidence</caption>" in rendered
