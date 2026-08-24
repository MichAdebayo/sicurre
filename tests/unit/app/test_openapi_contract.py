"""Contract drift checks for the deployed Sicurre API."""

from __future__ import annotations

from pathlib import Path

import yaml

from data_platform.api.main import create_app


def test_checked_in_openapi_matches_runtime() -> None:
    """Keep every published operation and schema aligned with FastAPI."""
    repository_root = Path(__file__).resolve().parents[3]
    documented = yaml.safe_load(
        (repository_root / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    )

    assert documented == create_app().openapi()


def test_email_scan_contract_preserves_safety_and_three_class_label() -> None:
    """Keep delivery safety separate from the three-class model decision."""

    repository_root = Path(__file__).resolve().parents[3]
    documented = yaml.safe_load(
        (repository_root / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    )
    schemas = documented["components"]["schemas"]

    assert schemas["EmailScanResponse"]["properties"]["verdict"]["enum"] == [
        "safe",
        "phishing",
        "quarantine",
    ]
    assert schemas["EmailScanResponse"]["properties"]["label"]["enum"] == [
        "phishing",
        "spam",
        "legitimate",
    ]


def test_successful_json_responses_are_explicitly_typed() -> None:
    """Prevent generic dictionaries from weakening generated response contracts."""
    runtime = create_app().openapi()
    generic_responses: list[str] = []

    for path, path_item in runtime["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status_code, response in operation.get("responses", {}).items():
                if not str(status_code).startswith("2") or status_code == "204":
                    continue
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                if not schema or schema == {} or schema.get("additionalProperties") is True:
                    generic_responses.append(f"{method.upper()} {path} ({status_code})")

    assert generic_responses == []
