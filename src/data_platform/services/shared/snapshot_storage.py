from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from core.config import get_settings


@dataclass(slots=True)
class SnapshotWriteResult:
    storage_uri: str
    content_hash: str
    size_bytes: int
    local_path: Path | None = None


class SnapshotStore(Protocol):
    def build_object_key(self, *, source_prefix: str, filename: str) -> str: ...

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult: ...


class LocalSnapshotStore:
    def __init__(self, *, root_dir: Path, repo_root: Path) -> None:
        self.root_dir = root_dir
        self.repo_root = repo_root

    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        return build_snapshot_object_key(prefix=source_prefix, filename=filename)

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult:
        del content_type
        local_path = self.root_dir / Path(object_key)
        await asyncio.to_thread(local_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(local_path.write_bytes, payload)
        return SnapshotWriteResult(
            storage_uri=self._to_storage_uri(local_path),
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            local_path=local_path,
        )

    def _to_storage_uri(self, local_path: Path) -> str:
        try:
            return str(local_path.relative_to(self.repo_root))
        except ValueError:
            return str(local_path)


class R2SnapshotStore:
    def __init__(
        self,
        *,
        bucket_name: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region_name: str = "auto",
        root_prefix: str = "raw-snapshots",
    ) -> None:
        self.bucket_name = bucket_name
        self.endpoint_url = self._normalize_endpoint(endpoint_url, bucket_name)
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region_name = region_name
        self.root_prefix = root_prefix.strip("/")

    def build_object_key(self, *, source_prefix: str, filename: str) -> str:
        prefix = source_prefix.strip("/")
        if self.root_prefix:
            prefix = f"{self.root_prefix}/{prefix}" if prefix else self.root_prefix
        return build_snapshot_object_key(prefix=prefix, filename=filename)

    async def write_snapshot(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
    ) -> SnapshotWriteResult:
        await asyncio.to_thread(
            self._put_object,
            object_key,
            payload,
            content_type,
        )
        return SnapshotWriteResult(
            storage_uri=f"r2://{self.bucket_name}/{object_key}",
            content_hash=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    def _put_object(self, object_key: str, payload: bytes, content_type: str) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for R2 snapshot storage") from exc

        client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region_name,
        )
        client.put_object(
            Bucket=self.bucket_name,
            Key=object_key,
            Body=payload,
            ContentType=content_type,
        )

    @staticmethod
    def _normalize_endpoint(endpoint_url: str, bucket_name: str) -> str:
        normalized = endpoint_url.rstrip("/")
        bucket_suffix = f"/{bucket_name}"
        if normalized.endswith(bucket_suffix):
            return normalized[: -len(bucket_suffix)]
        return normalized


def build_snapshot_store(
    *,
    local_root_dir: Path,
    repo_root: Path,
    source_key: str | None = None,
    backend: str | None = None,
) -> SnapshotStore:
    settings = get_settings()
    resolved_backend = (
        backend.strip().lower()
        if backend is not None
        else settings.resolve_snapshot_storage_backend(source_key=source_key)
    )

    if resolved_backend == "r2":
        required_settings = {
            "raw_snapshot_r2_bucket_name": settings.raw_snapshot_r2_bucket_name,
            "raw_snapshot_r2_endpoint_url": settings.raw_snapshot_r2_endpoint_url,
            "raw_snapshot_r2_access_key_id": settings.raw_snapshot_r2_access_key_id,
            "raw_snapshot_r2_secret_access_key": settings.raw_snapshot_r2_secret_access_key,
        }
        if missing_fields := [
            name for name, value in required_settings.items() if not value
        ]:
            missing = ", ".join(missing_fields)
            raise RuntimeError(f"Missing R2 snapshot settings: {missing}")

        return R2SnapshotStore(
            bucket_name=settings.raw_snapshot_r2_bucket_name,
            endpoint_url=settings.raw_snapshot_r2_endpoint_url,
            access_key_id=settings.raw_snapshot_r2_access_key_id,
            secret_access_key=settings.raw_snapshot_r2_secret_access_key,
            region_name=settings.raw_snapshot_r2_region,
            root_prefix=settings.raw_snapshot_prefix,
        )

    return LocalSnapshotStore(root_dir=local_root_dir, repo_root=repo_root)


def build_snapshot_object_key(*, prefix: str, filename: str) -> str:
    return PurePosixPath(prefix, filename).as_posix()
