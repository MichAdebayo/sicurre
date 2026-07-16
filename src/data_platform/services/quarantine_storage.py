"""Private raw-MIME custody for held quarantine messages."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from core.config import Settings, get_settings

QUARANTINE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _safe_identifier(value: str, *, field_name: str) -> str:
    """Validate one opaque storage-key segment against traversal characters."""
    if not QUARANTINE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid quarantine {field_name}")
    return value


@dataclass(frozen=True, slots=True)
class QuarantineObject:
    """Metadata persisted after a raw MIME object is written."""

    storage_uri: str
    content_hash: str
    size_bytes: int


class QuarantineStore(Protocol):
    """Storage operations needed by quarantine upload and release."""

    async def write(
        self, *, workspace_id: str, item_id: str, payload: bytes
    ) -> QuarantineObject: ...

    async def read(self, storage_uri: str) -> bytes: ...

    async def delete(self, storage_uri: str) -> None: ...


class LocalQuarantineStore:
    """Filesystem custody used only by local development and tests."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()

    def _path(self, workspace_id: str, item_id: str) -> Path:
        workspace = _safe_identifier(workspace_id, field_name="workspace_id")
        item = _safe_identifier(item_id, field_name="item_id")
        candidate = (self.root_dir / workspace / f"{item}.eml").resolve()
        if not candidate.is_relative_to(self.root_dir):
            raise ValueError("Quarantine object escapes the configured storage root")
        return candidate

    def _resolve_uri(self, storage_uri: str) -> Path:
        if not storage_uri.startswith("file://"):
            raise ValueError("Unsupported local quarantine URI")
        candidate = Path(storage_uri.removeprefix("file://")).resolve()
        if not candidate.is_relative_to(self.root_dir):
            raise ValueError("Quarantine object escapes the configured storage root")
        return candidate

    async def write(self, *, workspace_id: str, item_id: str, payload: bytes) -> QuarantineObject:
        """Write one raw MIME object with owner-only filesystem permissions."""
        path = self._path(workspace_id, item_id)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True, mode=0o700)
        await asyncio.to_thread(path.write_bytes, payload)
        await asyncio.to_thread(path.chmod, 0o600)
        return QuarantineObject(
            storage_uri=f"file://{path.resolve()}",
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    async def read(self, storage_uri: str) -> bytes:
        """Read a previously written raw MIME object."""
        return await asyncio.to_thread(self._resolve_uri(storage_uri).read_bytes)

    async def delete(self, storage_uri: str) -> None:
        """Delete a raw MIME object after release or expiry."""
        path = self._resolve_uri(storage_uri)
        await asyncio.to_thread(path.unlink, missing_ok=True)


class R2QuarantineStore:
    """Private Cloudflare R2 custody for production quarantine objects."""

    def __init__(self, settings: Settings) -> None:
        required = {
            "quarantine_r2_bucket_name": settings.quarantine_r2_bucket_name,
            "raw_snapshot_r2_endpoint_url": settings.raw_snapshot_r2_endpoint_url,
            "raw_snapshot_r2_access_key_id": settings.raw_snapshot_r2_access_key_id,
            "raw_snapshot_r2_secret_access_key": settings.raw_snapshot_r2_secret_access_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing quarantine R2 settings: {', '.join(missing)}")
        self.bucket = str(settings.quarantine_r2_bucket_name)
        self.prefix = settings.quarantine_r2_prefix.strip("/")
        self.client = _r2_client(settings)

    def _key(self, workspace_id: str, item_id: str) -> str:
        workspace = _safe_identifier(workspace_id, field_name="workspace_id")
        item = _safe_identifier(item_id, field_name="item_id")
        return PurePosixPath(self.prefix, workspace, f"{item}.eml").as_posix()

    def _parse_uri(self, storage_uri: str) -> str:
        prefix = f"r2://{self.bucket}/"
        if not storage_uri.startswith(prefix):
            raise ValueError("Quarantine object belongs to another bucket")
        key = storage_uri.removeprefix(prefix)
        key_path = PurePosixPath(key)
        prefix_path = PurePosixPath(self.prefix)
        if ".." in key_path.parts or key_path.parts[: len(prefix_path.parts)] != prefix_path.parts:
            raise ValueError("Quarantine object escapes the configured prefix")
        return key

    async def write(self, *, workspace_id: str, item_id: str, payload: bytes) -> QuarantineObject:
        """Write a private raw MIME object to R2."""
        key = self._key(workspace_id, item_id)
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="message/rfc822",
        )
        return QuarantineObject(
            storage_uri=f"r2://{self.bucket}/{key}",
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    async def read(self, storage_uri: str) -> bytes:
        """Read raw MIME bytes from R2."""
        response = await asyncio.to_thread(
            self.client.get_object,
            Bucket=self.bucket,
            Key=self._parse_uri(storage_uri),
        )
        return await asyncio.to_thread(response["Body"].read)

    async def delete(self, storage_uri: str) -> None:
        """Delete raw MIME bytes from R2."""
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=self.bucket,
            Key=self._parse_uri(storage_uri),
        )


def _r2_client(settings: Settings) -> Any:
    import boto3

    endpoint = str(settings.raw_snapshot_r2_endpoint_url).rstrip("/")
    bucket_suffix = f"/{settings.quarantine_r2_bucket_name}"
    if endpoint.endswith(bucket_suffix):
        endpoint = endpoint[: -len(bucket_suffix)]
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.raw_snapshot_r2_access_key_id,
        aws_secret_access_key=settings.raw_snapshot_r2_secret_access_key,
        region_name=settings.raw_snapshot_r2_region,
    )


def build_quarantine_store(settings: Settings | None = None) -> QuarantineStore:
    """Build the configured local or R2 quarantine store."""
    resolved = settings or get_settings()
    backend = resolved.quarantine_storage_backend.strip().lower()
    if backend == "local":
        return LocalQuarantineStore(resolved.quarantine_local_dir)
    if backend == "r2":
        return R2QuarantineStore(resolved)
    raise RuntimeError("SICURRE_QUARANTINE_STORAGE_BACKEND must be local or r2")
