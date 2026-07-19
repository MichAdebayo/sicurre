"""Unit tests for GitHubActionsGateway."""

from __future__ import annotations

import httpx
import pytest
import respx

from data_platform.services.shared.github_actions_gateway import (
    GitHubActionsGateway,
    GitHubDispatchError,
)

_DISPATCH_URL = (
    "https://api.github.com/repos/owner-test/sicurre-ml/actions/workflows/train.yml/dispatches"
)
_WORKFLOW_URL = "https://api.github.com/repos/owner-test/sicurre-ml/actions/workflows/train.yml"
LINEAGE = {
    "dataset_id": "545aaf99-05cd-4a4b-b31a-689265d873ae",
    "dataset_version": "base-20260718-144342",
    "dataset_sha256": "a" * 64,
}


@pytest.fixture
def gateway() -> GitHubActionsGateway:
    return GitHubActionsGateway(
        token="test-token",
        owner="owner-test",
        repo="sicurre-ml",
    )


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_training_success(gateway: GitHubActionsGateway) -> None:
    """204 response completes without error."""
    respx.post(_DISPATCH_URL).mock(return_value=httpx.Response(204))

    await gateway.dispatch_training(kaggle_slug="user/sicurre-data", **LINEAGE)

    assert respx.calls.call_count == 1
    request = respx.calls.last.request
    import json

    body = json.loads(request.content)
    assert body["ref"] == "main"
    assert body["inputs"]["training_dataset"] == "user/sicurre-data"
    assert body["inputs"]["dataset_id"] == LINEAGE["dataset_id"]
    assert body["inputs"]["dataset_version"] == LINEAGE["dataset_version"]
    assert body["inputs"]["dataset_sha256"] == LINEAGE["dataset_sha256"]


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_training_sends_bearer_token(
    gateway: GitHubActionsGateway,
) -> None:
    respx.post(_DISPATCH_URL).mock(return_value=httpx.Response(204))

    await gateway.dispatch_training(kaggle_slug="user/sicurre-data", **LINEAGE)

    auth_header = respx.calls.last.request.headers.get("Authorization", "")
    assert auth_header == "Bearer test-token"


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_training_raises_on_non_204(
    gateway: GitHubActionsGateway,
) -> None:
    """Any non-204 status raises GitHubDispatchError."""
    for status_code in (403, 404, 422, 500):
        respx.post(_DISPATCH_URL).mock(
            return_value=httpx.Response(status_code, json={"message": "err"})
        )

        with pytest.raises(GitHubDispatchError):
            await gateway.dispatch_training(kaggle_slug="user/sicurre-data", **LINEAGE)


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_training_custom_ref(gateway: GitHubActionsGateway) -> None:
    """Custom ref is forwarded in the request body."""
    respx.post(_DISPATCH_URL).mock(return_value=httpx.Response(204))

    await gateway.dispatch_training(kaggle_slug="user/sicurre-data", ref="main", **LINEAGE)

    import json

    body = json.loads(respx.calls.last.request.content)
    assert body["ref"] == "main"


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_training_custom_workflow() -> None:
    custom_url = (
        "https://api.github.com/repos/owner-test/sicurre-ml"
        "/actions/workflows/retrain.yml/dispatches"
    )
    respx.post(custom_url).mock(return_value=httpx.Response(204))

    gw = GitHubActionsGateway(token="tok", owner="owner-test", repo="sicurre-ml")
    await gw.dispatch_training(kaggle_slug="slug", workflow="retrain.yml", **LINEAGE)

    assert respx.calls.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_validate_training_receiver_accepts_active_workflow(
    gateway: GitHubActionsGateway,
) -> None:
    """An accessible active workflow passes release preflight validation."""
    respx.get(_WORKFLOW_URL).mock(return_value=httpx.Response(200, json={"state": "active"}))

    await gateway.validate_training_receiver()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("status_code", [403, 404, 500])
async def test_validate_training_receiver_rejects_inaccessible_workflow(
    gateway: GitHubActionsGateway,
    status_code: int,
) -> None:
    """An inaccessible workflow stops release before dataset publication."""
    respx.get(_WORKFLOW_URL).mock(
        return_value=httpx.Response(status_code, json={"message": "unavailable"})
    )

    with pytest.raises(GitHubDispatchError):
        await gateway.validate_training_receiver()
