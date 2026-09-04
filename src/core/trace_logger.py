"""
Semantic Trace Logger natively handling the Strict JSON Trace Schema for Sicurre.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal


class SemanticTraceLogger:
    def __init__(
        self,
        parent_type: str,
        child_target: str,
        domain: Literal["data_platform", "live_app"] = "data_platform",
        trace_id: str | None = None,
    ) -> None:
        """Initialize the Semantic Trace Logger enforcing strict lineage constraints."""
        self.parent_type = parent_type
        self.child_target = child_target
        self.domain = domain
        self._trace_id = trace_id or "run-pending"
        self.logger = logging.getLogger(f"trace.{child_target.lower()}")

    def set_trace_id(self, trace_id: str) -> None:
        """Bind the trace ID horizontally once the Ingestion Run is generated."""
        self._trace_id = str(trace_id)

    def trace(
        self,
        *,
        stage: Literal[
            "orchestration",
            "ingestion",
            "snapshot",
            "extraction",
            "normalization",
            "pii_scrubbing",
            "annotation",
            "dataset_freeze",
            "classification",
            "remediation",
        ],
        status: Literal["start", "success", "failed", "skipped"],
        message: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Emits a strictly formatted Semantic JSON Trace block."""
        payload = {
            "parent_type": self.parent_type,
            "child_target": self.child_target,
            "trace_id": self._trace_id,
            "domain": self.domain,
            "stage": stage,
            "status": status,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        }

        if entity_type:
            payload["entity_type"] = entity_type
        if entity_id:
            payload["entity_id"] = str(entity_id)
        if metrics:
            payload["metrics"] = metrics

        # ── Tier 1: Human-readable line (raw terminal / judge demo) ──────────
        _STATUS_ICON = {"start": "▶", "success": "✓", "failed": "✗", "skipped": "○"}
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        icon = _STATUS_ICON.get(status, "·")
        human_line = f"[{ts}] {icon} [{stage.upper()}] {message}"
        if metrics:
            human_line += "  · " + "  ".join(f"{k}={v}" for k, v in metrics.items())
        print(human_line, flush=True)

        # ── Tier 2: Strict JSON trace (parsed by Streamlit terminal renderer) ─
        json_output = json.dumps(payload, ensure_ascii=False)
        # Output directly to stdout so Streamlit subprocess interceptors can
        # safely JSON-parse each distinct trace line row by row.
        print(json_output, flush=True)

        # Mirror cleanly to traditional internal logs for redundancy context
        log_level = logging.ERROR if status == "failed" else logging.INFO
        stage_token = f"{stage}/{status}"
        context_parts = [self.child_target, stage_token, message]
        if entity_type or entity_id:
            entity_bits = [part for part in (entity_type, entity_id) if part]
            context_parts.append(f"entity={'/'.join(entity_bits)}")
        if metrics:
            rendered_metrics = ", ".join(
                f"{key}={value}" for key, value in sorted(metrics.items())
            )
            context_parts.append(f"metrics[{rendered_metrics}]")
        self.logger.log(log_level, " | ".join(context_parts))
