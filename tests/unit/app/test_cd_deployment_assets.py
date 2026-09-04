"""Deployment workflow asset contract tests."""

import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CD_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/cd.yml"


def test_cd_copies_every_declared_deployment_asset() -> None:
    """Ensure repository-backed provisioning files reach the remote host."""
    workflow = CD_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r'^\s+source: "([^"]+)"$', workflow, flags=re.MULTILINE)

    assert match is not None
    deployment_assets = match.group(1).split(",")
    missing = [asset for asset in deployment_assets if not (REPOSITORY_ROOT / asset).is_file()]

    assert not missing, f"CD references missing deployment assets: {missing}"
    assert "deploy/grafana/alerts/sicurre-alerts.json" in deployment_assets
    assert "deploy/grafana/dashboards/sicurre-controlled-exercise.json" in deployment_assets


def test_cd_transfers_every_module_the_provisioning_script_imports() -> None:
    """Close the converse gap: declared assets exist, but are they sufficient?"""
    workflow = CD_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r'^\s+source: "([^"]+)"$', workflow, flags=re.MULTILINE)
    assert match is not None
    deployment_assets = set(match.group(1).split(","))

    script_assets = [
        asset for asset in deployment_assets
        if asset.startswith("scripts/") and asset.endswith(".mjs")
    ]
    assert script_assets, "No provisioning scripts are transferred by CD"

    for asset in script_assets:
        source = (REPOSITORY_ROOT / asset).read_text(encoding="utf-8")
        relative_imports = re.findall(r'^import .*? from "(\.[^"]+)";', source, flags=re.MULTILINE)
        for relative_import in relative_imports:
            resolved = (REPOSITORY_ROOT / asset).parent / relative_import
            required = resolved.resolve().relative_to(REPOSITORY_ROOT).as_posix()
            assert required in deployment_assets, (
                f"{asset} imports {required}, which CD does not transfer"
            )
