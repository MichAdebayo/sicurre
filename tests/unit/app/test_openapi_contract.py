"""Contract drift checks for the deployed Sicurre API."""

from __future__ import annotations

from pathlib import Path

import yaml

from data_platform.api.main import create_app


def test_documented_openapi_paths_match_runtime() -> None:
    """Keep the hand-authored public contract aligned with every runtime route."""
    repository_root = Path(__file__).resolve().parents[3]
    documented = yaml.safe_load(
        (repository_root / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    )

    assert set(documented["paths"]) == set(create_app().openapi()["paths"])
