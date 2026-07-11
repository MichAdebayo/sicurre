from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class KagglePushError(Exception):
    """Raised when the kaggle datasets version call fails."""


class KaggleGateway:
    """Wraps the kaggle API client to push a new dataset version in-process.

    Runs in a thread executor so the async event loop is not blocked.
    Injectable — swap for a stub in tests.
    """

    def __init__(
        self,
        username: str,
        key: str,
        api_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._username = username
        self._key = key
        self._api_factory = api_factory or self._create_api

    @staticmethod
    def _create_api() -> Any:
        """Create the Kaggle client after credentials are present in the environment."""
        from kaggle import KaggleApi

        return KaggleApi()

    def _configure_credentials(self) -> None:
        """Expose the modern access token contract expected by Kaggle 2.x."""
        if self._key:
            os.environ["KAGGLE_API_TOKEN"] = self._key
            os.environ.pop("KAGGLE_KEY", None)
        if self._username:
            os.environ["KAGGLE_USERNAME"] = self._username

    async def push_version(
        self,
        *,
        slug: str,
        export_dir: Path,
        message: str,
    ) -> int:
        """Push a new dataset version and return the new version number.

        Raises KagglePushError if the API call fails.
        Runs in an executor to avoid blocking the event loop.
        """
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self._push_sync,
            slug,
            export_dir,
            message,
        )

    def _push_sync(self, slug: str, export_dir: Path, message: str) -> int:
        # 1. Apply IPv4 monkeypatch to prevent IPv6 connection hang
        orig_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = lambda h, p, *a, **kw: orig_getaddrinfo(
            h, p, socket.AF_INET, *a[1:] if a else 0, **kw
        )

        try:
            # Write dataset-metadata.json into the export directory if missing
            metadata_file = export_dir / "dataset-metadata.json"
            if not metadata_file.exists():
                logger.info("Writing dataset-metadata.json dynamically")
                title = slug.split("/")[-1].replace("-", " ").title()
                resources = [
                    {"path": item.name, "description": f"Sicurre {item.stem} split"}
                    for item in sorted(export_dir.glob("*.csv"))
                ]
                with open(metadata_file, "w") as f:
                    json.dump({"id": slug, "title": title, "resources": resources}, f)

            # Try authenticating using settings credentials first
            try:
                self._configure_credentials()
                api = self._api_factory()
                api.authenticate()
                # Test credentials by checking status of target dataset
                api.dataset_status(slug)
            except Exception as auth_err:
                logger.warning(
                    f"Kaggle authentication with settings credentials failed: {auth_err}. "
                    "Falling back to default kaggle.json credentials."
                )
                os.environ.pop("KAGGLE_USERNAME", None)
                os.environ.pop("KAGGLE_KEY", None)
                os.environ.pop("KAGGLE_API_TOKEN", None)
                api = self._api_factory()
                api.authenticate()

            logger.info(f"Uploading new dataset version to Kaggle: slug={slug}...")
            response = api.dataset_create_version(
                folder=str(export_dir),
                version_notes=message,
                quiet=True,
                convert_to_csv=False,
                dir_mode="tar",
            )

            # Extract version number if available in the response object
            version_num = getattr(response, "versionNumber", 0)
            if not version_num:
                url = getattr(response, "url", "")
                if url:
                    parts = url.rstrip("/").split("/")
                    if parts and parts[-1].isdigit():
                        version_num = int(parts[-1])
            return int(version_num) if version_num else 0
        except Exception as exc:
            response = getattr(exc, "response", None)
            response_text = ""
            if response is not None:
                response_text = getattr(response, "text", "") or ""
            detail = f"Kaggle push failed: {exc}"
            if response_text:
                detail = f"{detail} — response: {response_text[:1000]}"
            raise KagglePushError(detail) from exc
        finally:
            socket.getaddrinfo = orig_getaddrinfo

    @staticmethod
    def _parse_version_number(stdout: str) -> int:
        """Extract the version number from kaggle CLI output.

        The CLI prints a line like 'Dataset version is being created.'
        and sometimes 'Your dataset has been updated to version N'.
        Returns 0 when the version number cannot be parsed — callers
        should treat 0 as 'unknown but push succeeded'.
        """
        for line in stdout.splitlines():
            parts = line.strip().split()
            if "version" in parts:
                idx = parts.index("version")
                if idx + 1 < len(parts):
                    candidate = parts[idx + 1].rstrip(".")
                    if candidate.isdigit():
                        return int(candidate)
        return 0


def write_split_csv(rows: list[dict[str, object]], dest: Path) -> None:
    """Write a list of {text, label} dicts to a CSV file."""
    if not rows:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["text", "label"])
        writer.writeheader()
        writer.writerows(rows)
