"""A verdict records which model produced it."""

from __future__ import annotations

import inspect

from data_platform.api.routers import integrations
from data_platform.api.schemas.app_responses import ThreatLogResponse


def _scan_source() -> str:
    return inspect.getsource(integrations)


def test_the_identity_headers_are_read_from_the_response() -> None:
    source = _scan_source()
    assert "X-Sicurre-Model-Version" in source, "model version header is not read"
    assert "X-Sicurre-Model-Revision" in source, "model revision header is not read"


def test_the_identity_is_persisted_with_the_event() -> None:
    """Reading the header is useless if it never reaches the row."""
    source = _scan_source()
    insert = source[source.index("INSERT INTO app_inference_event") :]
    insert = insert[: insert.index(") VALUES")]
    assert "model_version" in insert, "model_version is not inserted"
    assert "model_revision" in insert, "model_revision is not inserted"


def test_the_insert_placeholders_match_its_columns() -> None:
    """A miscounted placeholder is a runtime failure on every scan."""
    source = _scan_source()
    start = source.index("INSERT INTO app_inference_event")
    block = source[start : source.index(")\n", source.index(") VALUES", start))]
    columns = block[block.index("(") + 1 : block.index(") VALUES")]
    column_count = len([c for c in columns.replace("\n", " ").split(",") if c.strip()])
    placeholder_count = block.count("?")
    assert column_count == placeholder_count, (
        f"{column_count} columns but {placeholder_count} placeholders"
    )


def test_identity_defaults_to_none_so_the_blocklist_path_cannot_crash() -> None:
    """A blocklist verdict never calls the model, so the names must still exist."""
    source = _scan_source()
    assert "model_version: str | None = None" in source
    assert "model_revision: str | None = None" in source


def test_the_threat_journal_exposes_the_model_identity() -> None:
    """Persisting it is not enough; the report cites the journal, not the table."""
    fields = ThreatLogResponse.model_fields
    assert "model_version" in fields
    assert "model_revision" in fields
    assert fields["model_version"].default is None, "must be optional for older rows"
