"""Provenance ships beside the CSV, never inside it.

The training contract is `text,label`. A third column would change what every
consumer parses, and — more importantly — a source name sitting next to the
text is a feature the model can learn from instead of the message. That is not
a hypothetical risk on this project: the deployed classifier was previously
found to have learned provenance rather than intent, because each class arrived
from its own corpus.

So the export answers "where did this split come from" in the sidecar
`metadata.json`, which a report can cite and a training run never reads.
"""

from __future__ import annotations

import pandas as pd

from data_platform.services.shared.dataset_export import _split_provenance


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "text": ["a", "b", "c", "d"],
            "label": ["phishing", "phishing", "legitimate", "spam"],
            "source_name": ["phishtank", "phishtank", "generated", None],
        }
    )


def test_counts_are_grouped_by_source() -> None:
    provenance = _split_provenance(_frame())
    assert provenance["by_source"]["phishtank"] == 2
    assert provenance["by_source"]["generated"] == 1


def test_a_missing_source_is_counted_not_dropped() -> None:
    """A row whose provenance is incomplete still belongs in the dataset."""
    provenance = _split_provenance(_frame())
    assert provenance["unattributed"] == 1
    assert sum(provenance["by_source"].values()) == 4


def test_source_by_label_exposes_a_single_source_class() -> None:
    """The cross-tab is the artifact that makes the confound visible."""
    provenance = _split_provenance(_frame())
    assert provenance["by_source_and_label"]["phishtank"] == {"phishing": 2}
    assert provenance["by_source_and_label"]["generated"] == {"legitimate": 1}


def test_counts_are_json_serialisable_integers() -> None:
    """numpy integers break json.dumps; the manifest is written as JSON."""
    import json

    provenance = _split_provenance(_frame())
    assert json.loads(json.dumps(provenance)) == provenance


def test_the_sentinel_says_unavailable_rather_than_empty() -> None:
    """"Could not look" must not read as "came from nowhere"."""
    from data_platform.services.shared.dataset_export import _UNAVAILABLE_PROVENANCE

    assert _UNAVAILABLE_PROVENANCE["available"] is False
    assert "by_source" not in _UNAVAILABLE_PROVENANCE
    assert _split_provenance(_frame())["available"] is True


def test_missing_lineage_tables_do_not_fail_the_export() -> None:
    """The CSV is the deliverable; provenance is commentary on it."""
    import sqlalchemy as sa

    from data_platform.services.shared.dataset_export import DatasetExportService

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE data_dataset (id TEXT, version_tag TEXT)"))
        conn.execute(
            sa.text("CREATE TABLE data_dataset_item (dataset_id TEXT, split_name TEXT,"
                    " normalized_message_id TEXT)")
        )
        conn.execute(
            sa.text("CREATE TABLE data_normalized_message (id TEXT, current_label TEXT)")
        )

    service = DatasetExportService.__new__(DatasetExportService)
    with engine.connect() as conn:
        result = service._read_provenance(conn, "any-version", sqlite=True)

    assert result == {}, "a missing lineage table must degrade, not raise"
