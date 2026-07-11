from __future__ import annotations

import httpx


class GitHubDispatchError(Exception):
    """Raised when the GitHub workflow_dispatch call fails."""


class GitHubActionsGateway:
    """Thin async wrapper around the GitHub Actions workflow_dispatch API.

    Injectable — swap for a stub in tests without making real HTTP calls.
    """

    _DISPATCH_URL = (
        "https://api.github.com/repos/{owner}/{repo}"
        "/actions/workflows/{workflow}/dispatches"
    )

    def __init__(self, token: str, owner: str, repo: str = "sicurre-ml") -> None:
        self._token = token
        self._owner = owner
        self._repo = repo

    async def dispatch_training(
        self,
        *,
        ref: str = "mlops",
        kaggle_slug: str,
        workflow: str = "train.yml",
    ) -> None:
        """POST workflow_dispatch to trigger train.yml on the ML repo.

        Raises GitHubDispatchError on any non-204 response.
        Always passes kaggle_slug explicitly so train.yml ignores its static secret.
        """
        url = self._DISPATCH_URL.format(
            owner=self._owner, repo=self._repo, workflow=workflow
        )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"ref": ref, "inputs": {"training_dataset": kaggle_slug}}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)

        if resp.status_code != 204:
            raise GitHubDispatchError(
                f"workflow_dispatch failed: HTTP {resp.status_code}"
            )
