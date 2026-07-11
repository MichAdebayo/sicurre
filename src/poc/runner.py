"""Sicurre POC — Pipeline runner subprocess helper.

Runs Makefile targets as subprocesses and yields structured JSON trace lines
back to the Streamlit app for real-time rendering.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Generator

ROOT_DIR = Path(__file__).resolve().parents[2]


def _is_trace_line(line: str) -> dict | None:
    """Attempt to parse a line as a SemanticTraceLogger JSON payload."""
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
        if "stage" in payload and "status" in payload:
            return payload
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def run_pipeline_step(
    command: list[str],
    *,
    cwd: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> Generator[dict, None, int]:
    """Run a subprocess, yielding structured trace events and raw log lines.

    Each yielded dict has at minimum:
        {"type": "trace"|"log", "content": ...}

    For trace events, "content" is the full parsed JSON payload.
    For raw logs, "content" is the raw string.

    Returns the subprocess exit code.
    """
    import os

    env = {**os.environ, **(env_overrides or {})}
    proc = subprocess.Popen(
        command,
        cwd=str(cwd or ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        trace = _is_trace_line(line)
        if trace:
            yield {"type": "trace", "content": trace}
        else:
            yield {"type": "log", "content": line.rstrip()}

    proc.wait()
    return proc.returncode


def make_target(target: str, **env_overrides: str) -> Generator[dict, None, int]:
    """Convenience wrapper to run a Makefile target."""
    return run_pipeline_step(
        ["make", target],
        cwd=ROOT_DIR,
        env_overrides=env_overrides,
    )
