"""Read-only Cloudflare R2 client for base ingestion.

All base ingest scripts import this to stream raw data from R2 without
touching local disk:

- Small files (CSVs, JSONs, TXTs) → ``download_bytes()``  → returns bytes
- Large files (parquets, SQLite)   → ``download_to_tempfile()`` → auto-deleting
  temp file inside a dedicated :class:`tempfile.TemporaryDirectory`

Credentials are resolved from ``SICURRE_RAW_SNAPSHOT_R2_*`` environment
variables (with ``.env`` auto-loaded).  A ``RuntimeError`` is raised at
construction time if any required variable is absent so misconfiguration
fails loudly before any network I/O is attempted.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import boto3
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Resolve repo root from this file's location:
# src/data_platform/services/shared/r2_read_client.py → 4 parents up
_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class R2Object:
    """Metadata returned by :meth:`R2ReadClient.list_objects`."""

    key: str
    size_bytes: int
    etag: str


class R2ReadClient:
    """Synchronous read-only S3/R2 client for base ingestion scripts.

    Boto3 has no async API, so all methods here are synchronous.  They are
    safe to call from a ``run_in_executor`` context if needed in async code,
    but all current callers use them in sync ``__main__`` guards or sync
    helper functions.
    """

    def __init__(self) -> None:
        load_dotenv(_REPO_ROOT / ".env")

        self._bucket: str = os.environ.get(
            "SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME", "sicurre-raw"
        )
        endpoint = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ENDPOINT_URL")
        access_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_ACCESS_KEY_ID")
        secret_key = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_SECRET_ACCESS_KEY")
        region = os.environ.get("SICURRE_RAW_SNAPSHOT_R2_REGION", "auto")

        if not all([endpoint, access_key, secret_key]):
            raise RuntimeError(
                "R2 credentials not configured — set "
                "SICURRE_RAW_SNAPSHOT_R2_ENDPOINT_URL, "
                "SICURRE_RAW_SNAPSHOT_R2_ACCESS_KEY_ID, and "
                "SICURRE_RAW_SNAPSHOT_R2_SECRET_ACCESS_KEY in .env"
            )

        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def list_objects(self, prefix: str, suffix: str = "") -> list[R2Object]:
        """Return all objects under *prefix*, optionally filtered by *suffix*.

        A trailing slash is added to *prefix* if absent so sibling-prefix
        collisions are avoided (e.g. ``raw-snapshots/base/api/phishtank``
        will not inadvertently match ``raw-snapshots/base/api/phishtank2``).

        Results are sorted by key for deterministic processing order.
        """
        if not prefix.endswith("/"):
            prefix = prefix + "/"
        paginator = self._s3.get_paginator("list_objects_v2")
        objects: list[R2Object] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key: str = obj["Key"]
                if suffix and not key.endswith(suffix):
                    continue
                objects.append(
                    R2Object(
                        key=key,
                        size_bytes=obj["Size"],
                        etag=obj.get("ETag", "").strip('"'),
                    )
                )
        objects.sort(key=lambda o: o.key)
        logger.debug(
            "list_objects(%r, suffix=%r) → %d objects", prefix, suffix, len(objects)
        )
        return objects

    def download_bytes(self, key: str) -> bytes:
        """Download an R2 object entirely into memory.

        Use for small files: CSVs, JSONs, TXTs.  Not suitable for multi-MB
        files where :meth:`download_to_tempfile` avoids heap pressure.
        """
        buf = io.BytesIO()
        self._s3.download_fileobj(self._bucket, key, buf)
        data = buf.getvalue()
        logger.debug("download_bytes(%r) → %d bytes", key, len(data))
        return data

    @contextmanager
    def download_to_tempfile(self, key: str) -> Generator[Path, None, None]:
        """Download an R2 object to an auto-deleting temporary file.

        The file lives inside a dedicated :class:`tempfile.TemporaryDirectory`
        so the parent directory contains *only* this file — no stray
        ``*.parquet`` files from other concurrent runs.  The directory and
        all its contents are deleted when the context exits.

        Use for large files that require a filesystem path (parquets, SQLite).

        Example::

            with r2.download_to_tempfile("raw-snapshots/base/database/external_threats.db") as path:
                connector = LegacyDbConnector(db_url=f"sqlite+aiosqlite:///{path}")
                ...
            # path and its parent directory are deleted here
        """
        filename = key.rsplit("/", 1)[-1]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / filename
            logger.info("Downloading r2://%s/%s → %s", self._bucket, key, tmp_path)
            self._s3.download_file(self._bucket, key, str(tmp_path))
            logger.info(
                "Download complete: %s (%.1f KB)",
                filename,
                tmp_path.stat().st_size / 1024,
            )
            yield tmp_path
        logger.debug("Temp directory for %r deleted", filename)
