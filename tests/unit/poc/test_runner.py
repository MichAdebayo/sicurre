"""Tests for structured terminal evidence parsing."""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from poc.runner import _is_trace_line, make_target, run_pipeline_step


def test_trace_line_requires_stage_and_status() -> None:
    payload = {"stage": "ingestion", "status": "success", "records": 4}
    assert _is_trace_line(json.dumps(payload)) == payload
    assert _is_trace_line('{"stage": "ingestion"}') is None


def test_plain_or_invalid_output_is_not_a_trace() -> None:
    assert _is_trace_line("Downloaded 4 records") is None
    assert _is_trace_line("{invalid-json") is None


class FakeProcess:
    def __init__(self) -> None:
        self.stdout: Iterator[str] = iter(
            [
                '{"stage":"extract","status":"success"}\n',
                "plain output\n",
            ]
        )
        self.returncode = 3

    def wait(self) -> None:
        return None


def test_pipeline_runner_yields_trace_and_log_and_returns_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    generator = run_pipeline_step(
        ["make", "demo"], cwd=tmp_path, env_overrides={"POC_TEST": "true"}
    )
    assert next(generator) == {
        "type": "trace",
        "content": {"stage": "extract", "status": "success"},
    }
    assert next(generator) == {"type": "log", "content": "plain output"}
    with pytest.raises(StopIteration) as completed:
        next(generator)
    assert completed.value.value == 3
    assert captured["command"] == ["make", "demo"]
    assert captured["cwd"] == str(tmp_path)
    assert captured["env"]["POC_TEST"] == "true"


def test_make_target_uses_make_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_runner(
        command: list[str], *, cwd: Path, env_overrides: dict[str, str]
    ) -> Iterator[dict[str, object]]:
        captured.update(command=command, cwd=cwd, env=env_overrides)
        yield {"type": "log", "content": "ok"}

    monkeypatch.setattr("poc.runner.run_pipeline_step", fake_runner)
    assert list(make_target("poc-replay-frozen", SAFE="true")) == [{"type": "log", "content": "ok"}]
    assert captured["command"] == ["make", "poc-replay-frozen"]
    assert captured["env"] == {"SAFE": "true"}
