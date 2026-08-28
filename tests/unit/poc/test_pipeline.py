"""Tests for POC pipeline operation safety boundaries."""

import subprocess
from collections.abc import Iterator

import pytest

from poc.config import PocSettings
from poc.pipeline import (
    OPERATIONS,
    build_poc_process_env,
    stream_operation,
    validate_operation,
)


def settings(**overrides: object) -> PocSettings:
    values = {
        "database_url": "sqlite:////tmp/poc-auth.db",
        "data_platform_database_url": "sqlite:////tmp/poc-data.db",
        "inference_api_url": "http://127.0.0.1:8000/v1/classify",
        "inference_api_key": "test-key",
        "admin_password": "admin-secret",
        "viewer_password": "viewer-secret",
    }
    values.update(overrides)
    return PocSettings(_env_file=None, **values)


def test_local_operations_are_allowed_by_default() -> None:
    validate_operation(OPERATIONS["base_replay"], settings())
    validate_operation(OPERATIONS["incremental_demo"], settings())
    validate_operation(OPERATIONS["release_preview"], settings())


def test_process_environment_uses_only_poc_runtime_values() -> None:
    configured = settings(snapshot_prefix="demonstrations/jury")
    environment = build_poc_process_env(configured)
    assert environment["SICURRE_POC_MODE"] == "true"
    assert (
        environment["SICURRE_DATA_PLATFORM_DATABASE_URL"] == configured.data_platform_database_url
    )
    assert environment["SICURRE_POC_SNAPSHOT_PREFIX"] == "demonstrations/jury"
    assert environment["SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND"] == "local"
    assert environment["SICURRE_TRAINING_DATASET_SNAPSHOT_STORAGE_BACKEND"] == "local"


class FakeProcess:
    """Small subprocess stand-in for output and exit-code tests."""

    def __init__(self, lines: list[str], return_code: int) -> None:
        self.stdout: Iterator[str] = iter(lines)
        self.return_code = return_code

    def wait(self) -> int:
        return self.return_code


def test_stream_operation_uses_fixed_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return FakeProcess(["first\n", "second\n"], 0)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    output = list(stream_operation("base_replay", settings()))
    assert captured["command"] == ["make", "poc-replay-frozen"]
    assert output == ["first", "second"]


def test_stream_operation_propagates_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(["failed\n"], 7),
    )
    with pytest.raises(subprocess.CalledProcessError) as error:
        list(stream_operation("base_replay", settings()))
    assert error.value.returncode == 7
