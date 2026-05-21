from __future__ import annotations

import asyncio
import csv
import os
import subprocess
import tempfile
from pathlib import Path


class KagglePushError(Exception):
    """Raised when the kaggle datasets version call fails."""


class KaggleGateway:
    """Wraps the kaggle CLI to push a new dataset version.

    Runs the CLI in a thread executor so the async event loop is not blocked.
    Injectable — swap for a stub in tests.
    """

    def __init__(self, username: str, key: str) -> None:
        self._username = username
        self._key = key

    async def push_version(
        self,
        *,
        slug: str,
        export_dir: Path,
        message: str,
    ) -> int:
        """Push a new dataset version and return the new version number.

        Raises KagglePushError if the CLI exits non-zero.
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
        env = {
            **os.environ,
            "KAGGLE_USERNAME": self._username,
            "KAGGLE_KEY": self._key,
        }
        result = subprocess.run(
            [
                "kaggle",
                "datasets",
                "version",
                "--path",
                str(export_dir),
                "--message",
                message,
                "--dir-mode",
                "tar",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise KagglePushError(
                f"kaggle CLI exited {result.returncode}: {result.stderr.strip()}"
            )
        return self._parse_version_number(result.stdout)

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
