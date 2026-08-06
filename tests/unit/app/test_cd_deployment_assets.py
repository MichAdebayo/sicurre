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
