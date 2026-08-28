"""Safe, fixed-command pipeline operations exposed by the POC."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from poc.config import ROOT_DIR, PocSettings


class PipelineScope(StrEnum):
    """External impact classification for a POC operation."""

    LOCAL = "local"
    EXTERNAL_READ_LOCAL_WRITE = "external_read_local_write"
    PRODUCTION_FORBIDDEN = "production_forbidden"


@dataclass(frozen=True)
class PipelineOperation:
    """A fixed pipeline command approved for the demonstration UI."""

    key: str
    command: tuple[str, ...]
    scope: PipelineScope


OPERATIONS = {
    "base_replay": PipelineOperation(
        key="base_replay",
        command=("make", "poc-replay-frozen"),
        scope=PipelineScope.LOCAL,
    ),
    "incremental_demo": PipelineOperation(
        key="incremental_demo",
        command=("make", "poc-cron-demo"),
        scope=PipelineScope.EXTERNAL_READ_LOCAL_WRITE,
    ),
    "release_preview": PipelineOperation(
        key="release_preview",
        command=("make", "poc-release-preview"),
        scope=PipelineScope.LOCAL,
    ),
}


def build_poc_process_env(settings: PocSettings) -> dict[str, str]:
    """Build an isolated process environment for POC pipeline commands."""
    env = dict(os.environ)
    env.update(
        {
            "SICURRE_POC_MODE": "true",
            "SICURRE_DATABASE_URL": settings.database_url,
            "SICURRE_DATA_PLATFORM_DATABASE_URL": settings.data_platform_database_url,
            "INFERENCE_API_URL": settings.inference_api_url,
            "INFERENCE_API_KEY": settings.inference_api_key,
            "SICURRE_POC_SNAPSHOT_PREFIX": settings.snapshot_prefix,
            "SICURRE_POC_SNAPSHOT_DIR": str(settings.snapshot_dir),
            "SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND": "local",
            "SICURRE_TRAINING_DATASET_SNAPSHOT_STORAGE_BACKEND": "local",
        }
    )
    return env


def validate_operation(operation: PipelineOperation, settings: PocSettings) -> None:
    """Reject operations whose external impact has not been explicitly enabled."""
    if operation.scope is PipelineScope.PRODUCTION_FORBIDDEN:
        raise PermissionError("Production operations are never available from the POC.")


def stream_operation(
    operation_key: str,
    settings: PocSettings,
    *,
    cwd: Path = ROOT_DIR,
) -> Iterator[str]:
    """Run one approved command and stream its combined output."""
    operation = OPERATIONS[operation_key]
    validate_operation(operation, settings)
    process = subprocess.Popen(
        list(operation.command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=build_poc_process_env(settings),
        bufsize=1,
    )
    assert process.stdout is not None
    yield from (line.rstrip() for line in process.stdout)
    return_code = process.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, operation.command)
