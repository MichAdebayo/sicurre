"""Tests for deterministic OpenAPI contract generation."""

import importlib.util
from pathlib import Path
from types import ModuleType

import yaml
from pytest import CaptureFixture, MonkeyPatch


def _load_generator() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "data_platform" / "generate_openapi.py"
    spec = importlib.util.spec_from_file_location("generate_openapi", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generate_openapi = _load_generator()


def test_generated_openapi_is_deterministic_and_complete() -> None:
    """The rendered contract must preserve the complete runtime schema."""
    document = generate_openapi.generated_openapi()

    assert document["openapi"].startswith("3.1")
    assert "/v1/threats" in document["paths"]
    assert yaml.safe_load(generate_openapi.render_openapi(document)) == document


def test_check_openapi_handles_missing_current_and_stale_files(tmp_path: Path) -> None:
    """Drift detection must distinguish absent, current, and stale contracts."""
    output = tmp_path / "openapi.yaml"
    assert generate_openapi.check_openapi(output) is False

    document = generate_openapi.generated_openapi()
    output.write_text(generate_openapi.render_openapi(document), encoding="utf-8")
    assert generate_openapi.check_openapi(output) is True

    output.write_text("openapi: 3.1.0\n", encoding="utf-8")
    assert generate_openapi.check_openapi(output) is False


def test_main_generates_and_checks_contract(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    """The CLI must write a contract and accept the resulting file in check mode."""
    output = tmp_path / "nested" / "openapi.yaml"
    monkeypatch.setattr("sys.argv", ["generate_openapi.py", "--output", str(output)])

    assert generate_openapi.main() == 0
    assert output.exists()
    assert "Generated OpenAPI contract" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv",
        ["generate_openapi.py", "--check", "--output", str(output)],
    )
    assert generate_openapi.main() == 0
    assert "OpenAPI contract is current" in capsys.readouterr().out


def test_main_reports_contract_drift(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    """Check mode must fail with an actionable regeneration instruction."""
    output = tmp_path / "openapi.yaml"
    monkeypatch.setattr(
        "sys.argv",
        ["generate_openapi.py", "--check", "--output", str(output)],
    )

    assert generate_openapi.main() == 1
    assert "make openapi" in capsys.readouterr().err
