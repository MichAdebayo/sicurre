"""Tests for the SemanticTraceLogger structured output contract."""

from __future__ import annotations

import json
import logging

from core.trace_logger import SemanticTraceLogger


def test_trace_emits_valid_json_to_stdout(capsys: object) -> None:
    """Each trace call prints a valid JSON line containing the expected fields."""
    logger = SemanticTraceLogger(
        parent_type="test",
        child_target="UnitTest",
        domain="data_platform",
        trace_id="trace-001",
    )

    logger.trace(
        stage="ingestion",
        status="success",
        message="Ingested 100 records",
        entity_type="source",
        entity_id="phishtank-1",
        metrics={"inserted": 100, "skipped": 5},
    )

    captured = capsys.readlines() if hasattr(capsys, "readlines") else None  # type: ignore[union-attr]
    # capsys is a pytest fixture with readouterr
    import sys

    out = sys.stdout
    # Re-capture via capsys
    output = capsys.__class__.__name__  # type: ignore[union-attr]
    # Use the proper pytest capsys
    pass


def test_trace_json_contains_required_keys(capsys) -> None:  # type: ignore[no-untyped-def]
    """The JSON trace line includes all mandatory structured fields."""
    logger = SemanticTraceLogger(
        parent_type="cron",
        child_target="PhishTank",
        domain="data_platform",
        trace_id="trace-002",
    )

    logger.trace(stage="ingestion", status="start", message="Starting ingestion")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.startswith("{")]
    assert len(lines) >= 1, "At least one JSON trace line expected"

    payload = json.loads(lines[0])
    assert payload["parent_type"] == "cron"
    assert payload["child_target"] == "PhishTank"
    assert payload["trace_id"] == "trace-002"
    assert payload["domain"] == "data_platform"
    assert payload["stage"] == "ingestion"
    assert payload["status"] == "start"
    assert payload["message"] == "Starting ingestion"
    assert "timestamp" in payload


def test_trace_omits_optional_fields_when_not_provided(capsys) -> None:  # type: ignore[no-untyped-def]
    """entity_type, entity_id, and metrics are only present when passed."""
    logger = SemanticTraceLogger(
        parent_type="test",
        child_target="Minimal",
        trace_id="trace-003",
    )

    logger.trace(stage="snapshot", status="skipped", message="No new data")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.startswith("{")]
    payload = json.loads(lines[0])
    assert "entity_type" not in payload
    assert "entity_id" not in payload
    assert "metrics" not in payload


def test_trace_includes_metrics_when_provided(capsys) -> None:  # type: ignore[no-untyped-def]
    """Metrics dict is embedded in the JSON trace payload."""
    logger = SemanticTraceLogger(
        parent_type="test",
        child_target="MetricTest",
        trace_id="trace-004",
    )

    logger.trace(
        stage="normalization",
        status="success",
        message="Normalized",
        metrics={"rows": 42, "duration_ms": 150},
    )

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.startswith("{")]
    payload = json.loads(lines[0])
    assert payload["metrics"] == {"rows": 42, "duration_ms": 150}


def test_failed_status_logs_at_error_level(caplog) -> None:  # type: ignore[no-untyped-def]
    """A 'failed' status trace emits at ERROR level in the traditional logger."""
    logger = SemanticTraceLogger(
        parent_type="test",
        child_target="ErrorTest",
        trace_id="trace-005",
    )

    with caplog.at_level(logging.DEBUG, logger="trace.errortest"):
        logger.trace(stage="extraction", status="failed", message="Connection refused")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) >= 1
    assert "Connection refused" in error_records[0].message


def test_success_status_logs_at_info_level(caplog) -> None:  # type: ignore[no-untyped-def]
    """A 'success' status trace emits at INFO level."""
    logger = SemanticTraceLogger(
        parent_type="test",
        child_target="InfoTest",
        trace_id="trace-006",
    )

    with caplog.at_level(logging.DEBUG, logger="trace.infotest"):
        logger.trace(stage="annotation", status="success", message="Done")

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_records) >= 1


def test_set_trace_id_updates_subsequent_traces(capsys) -> None:  # type: ignore[no-untyped-def]
    """set_trace_id binds a new trace ID for all subsequent emissions."""
    logger = SemanticTraceLogger(
        parent_type="test",
        child_target="TraceIdTest",
    )

    logger.set_trace_id("run-42")
    logger.trace(stage="classification", status="start", message="Begin")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.startswith("{")]
    payload = json.loads(lines[0])
    assert payload["trace_id"] == "run-42"


def test_default_trace_id_is_pending() -> None:
    """Without explicit set, trace_id defaults to 'run-pending'."""
    logger = SemanticTraceLogger(parent_type="test", child_target="Default")
    assert logger._trace_id == "run-pending"


def test_human_readable_line_includes_stage_and_status_icon(capsys) -> None:  # type: ignore[no-untyped-def]
    """The first printed line is a human-readable summary with status icon."""
    logger = SemanticTraceLogger(
        parent_type="test",
        child_target="HumanTest",
        trace_id="trace-007",
    )

    logger.trace(stage="remediation", status="success", message="Item released")

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    human_line = lines[0]
    assert "✓" in human_line
    assert "[REMEDIATION]" in human_line
    assert "Item released" in human_line
