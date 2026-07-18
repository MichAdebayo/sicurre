from __future__ import annotations

import httpx


class GitHubDispatchError(Exception):
    """Raised when the GitHub workflow_dispatch call fails."""


class GitHubActionsGateway:
    """Thin async wrapper around the GitHub Actions workflow_dispatch API.

    Injectable — swap for a stub in tests without making real HTTP calls.
    """

    _DISPATCH_URL = (
        "https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
    )
    _WORKFLOW_URL = "https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}"

    def __init__(self, token: str, owner: str, repo: str = "sicurre-ml") -> None:
        self._token = token
        self._owner = owner
        self._repo = repo

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def validate_training_receiver(self, workflow: str = "train.yml") -> None:
        """Confirm that the token can access an active training workflow."""
        url = self._WORKFLOW_URL.format(owner=self._owner, repo=self._repo, workflow=workflow)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=self._headers())
        if response.status_code != 200 or response.json().get("state") != "active":
            raise GitHubDispatchError(
                f"training receiver validation failed: HTTP {response.status_code}"
            )

    async def dispatch_training(
        self,
        *,
        ref: str = "main",
        kaggle_slug: str,
        workflow: str = "train.yml",
    ) -> None:
        """POST workflow_dispatch to trigger train.yml on the ML repo.

        Raises GitHubDispatchError on any non-204 response.
        Always passes kaggle_slug explicitly so train.yml ignores its static secret.
        """
        url = self._DISPATCH_URL.format(owner=self._owner, repo=self._repo, workflow=workflow)
        payload = {"ref": ref, "inputs": {"training_dataset": kaggle_slug}}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)

        if resp.status_code != 204:
            raise GitHubDispatchError(f"workflow_dispatch failed: HTTP {resp.status_code}")
