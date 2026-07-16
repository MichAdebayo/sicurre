"""Tests for local quarantine storage: write, read, delete, and path traversal protection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from data_platform.services.quarantine_storage import (
    LocalQuarantineStore,
    QuarantineObject,
    R2QuarantineStore,
    build_quarantine_store,
)


@pytest.fixture
def store(tmp_path: Path) -> LocalQuarantineStore:
    """Create a local quarantine store rooted in a temporary directory."""
    return LocalQuarantineStore(root_dir=tmp_path)


@pytest.mark.asyncio
async def test_write_creates_eml_file(store: LocalQuarantineStore, tmp_path: Path) -> None:
    """write() creates a .eml file with the given payload."""
    result = await store.write(workspace_id="ws-1", item_id="item-1", payload=b"MIME data")

    assert isinstance(result, QuarantineObject)
    assert result.storage_uri.startswith("file://")
    assert result.content_hash  # non-empty SHA-256
    assert result.size_bytes == len(b"MIME data")

    written_path = Path(result.storage_uri.removeprefix("file://"))
    assert written_path.exists()
    assert written_path.read_bytes() == b"MIME data"


@pytest.mark.asyncio
async def test_read_returns_written_content(store: LocalQuarantineStore) -> None:
    """read() returns exactly the bytes that write() stored."""
    payload = b"Subject: Test\r\nFrom: a@b.com\r\n\r\nBody"
    obj = await store.write(workspace_id="ws-1", item_id="item-2", payload=payload)

    recovered = await store.read(obj.storage_uri)

    assert recovered == payload


@pytest.mark.asyncio
async def test_delete_removes_file(store: LocalQuarantineStore) -> None:
    """delete() removes the stored .eml file."""
    obj = await store.write(workspace_id="ws-1", item_id="item-3", payload=b"payload")
    written_path = Path(obj.storage_uri.removeprefix("file://"))
    assert written_path.exists()

    await store.delete(obj.storage_uri)

    assert not written_path.exists()


@pytest.mark.asyncio
async def test_delete_idempotent_on_missing_file(store: LocalQuarantineStore) -> None:
    """delete() does not raise if the file was already deleted."""
    obj = await store.write(workspace_id="ws-1", item_id="item-4", payload=b"data")
    await store.delete(obj.storage_uri)
    await store.delete(obj.storage_uri)  # should not raise


@pytest.mark.asyncio
async def test_read_rejects_path_traversal(store: LocalQuarantineStore, tmp_path: Path) -> None:
    """read() rejects URIs that escape the root directory."""
    evil_uri = f"file://{tmp_path.parent / 'escape.eml'}"

    with pytest.raises(ValueError, match="escapes"):
        await store.read(evil_uri)


@pytest.mark.asyncio
async def test_delete_rejects_path_traversal(store: LocalQuarantineStore, tmp_path: Path) -> None:
    """delete() rejects URIs that escape the root directory."""
    evil_uri = f"file://{tmp_path.parent / 'escape.eml'}"

    with pytest.raises(ValueError, match="escapes"):
        await store.delete(evil_uri)


@pytest.mark.asyncio
async def test_read_rejects_non_file_uri(store: LocalQuarantineStore) -> None:
    """read() rejects URIs with unsupported schemes."""
    with pytest.raises(ValueError, match="Unsupported"):
        await store.read("s3://bucket/key")


@pytest.mark.asyncio
async def test_write_computes_correct_sha256(store: LocalQuarantineStore) -> None:
    """write() returns the correct SHA-256 content hash."""
    import hashlib

    payload = b"deterministic content"
    expected_hash = hashlib.sha256(payload).hexdigest()

    obj = await store.write(workspace_id="ws-1", item_id="item-5", payload=payload)

    assert obj.content_hash == expected_hash


@pytest.mark.asyncio
async def test_workspace_isolation_on_disk(store: LocalQuarantineStore, tmp_path: Path) -> None:
    """Items from different workspaces are stored in separate subdirectories."""
    obj_a = await store.write(workspace_id="ws-a", item_id="item-1", payload=b"A")
    obj_b = await store.write(workspace_id="ws-b", item_id="item-1", payload=b"B")

    path_a = Path(obj_a.storage_uri.removeprefix("file://"))
    path_b = Path(obj_b.storage_uri.removeprefix("file://"))

    assert path_a.parent.name == "ws-a"
    assert path_b.parent.name == "ws-b"
    assert path_a.read_bytes() == b"A"
    assert path_b.read_bytes() == b"B"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_id", "item_id"),
    [
        ("../outside", "item-1"),
        ("/absolute", "item-1"),
        ("ws-1", "../outside"),
        ("ws-1", "nested/item"),
        ("ws\\outside", "item-1"),
    ],
)
async def test_write_rejects_unsafe_storage_identifiers(
    store: LocalQuarantineStore,
    tmp_path: Path,
    workspace_id: str,
    item_id: str,
) -> None:
    """write() cannot create a file outside its configured custody root."""
    with pytest.raises(ValueError, match="Invalid quarantine"):
        await store.write(workspace_id=workspace_id, item_id=item_id, payload=b"sensitive")

    assert not (tmp_path.parent / "outside" / "item-1.eml").exists()


def test_build_quarantine_store_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """build_quarantine_store creates a LocalQuarantineStore when backend=local."""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.quarantine_storage_backend = "local"
    mock_settings.quarantine_local_dir = tmp_path

    result = build_quarantine_store(mock_settings)

    assert isinstance(result, LocalQuarantineStore)
    assert result.root_dir == tmp_path


def test_build_quarantine_store_invalid_backend() -> None:
    """build_quarantine_store raises on unknown backends."""
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.quarantine_storage_backend = "gcs"

    with pytest.raises(RuntimeError, match="local or r2"):
        build_quarantine_store(mock_settings)


def _r2_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "quarantine_r2_bucket_name": "private-quarantine",
        "quarantine_r2_prefix": "quarantine",
        "raw_snapshot_r2_endpoint_url": "https://account.r2.cloudflarestorage.com",
        "raw_snapshot_r2_access_key_id": "access",
        "raw_snapshot_r2_secret_access_key": "secret",
        "raw_snapshot_r2_region": "auto",
        "quarantine_storage_backend": "r2",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_r2_store_rejects_missing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2 custody fails closed when any required credential is absent."""
    monkeypatch.setattr("data_platform.services.quarantine_storage._r2_client", MagicMock())

    with pytest.raises(RuntimeError, match="raw_snapshot_r2_access_key_id"):
        R2QuarantineStore(_r2_settings(raw_snapshot_r2_access_key_id=None))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_r2_store_round_trip_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2 operations preserve the private bucket, prefix, MIME type, and bytes."""
    body = MagicMock()
    body.read.return_value = b"original MIME"
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    monkeypatch.setattr("data_platform.services.quarantine_storage._r2_client", lambda _: client)
    store = R2QuarantineStore(_r2_settings())  # type: ignore[arg-type]

    stored = await store.write(
        workspace_id="workspace-1", item_id="message-1", payload=b"original MIME"
    )
    recovered = await store.read(stored.storage_uri)
    await store.delete(stored.storage_uri)

    assert stored.storage_uri == ("r2://private-quarantine/quarantine/workspace-1/message-1.eml")
    assert recovered == b"original MIME"
    client.put_object.assert_called_once_with(
        Bucket="private-quarantine",
        Key="quarantine/workspace-1/message-1.eml",
        Body=b"original MIME",
        ContentType="message/rfc822",
    )
    client.get_object.assert_called_once_with(
        Bucket="private-quarantine",
        Key="quarantine/workspace-1/message-1.eml",
    )
    client.delete_object.assert_called_once_with(
        Bucket="private-quarantine",
        Key="quarantine/workspace-1/message-1.eml",
    )


@pytest.mark.parametrize(
    "storage_uri",
    [
        "r2://another-bucket/quarantine/workspace/item.eml",
        "r2://private-quarantine/other/workspace/item.eml",
        "r2://private-quarantine/quarantine/../secret.eml",
    ],
)
def test_r2_store_rejects_foreign_or_escaping_uri(
    monkeypatch: pytest.MonkeyPatch, storage_uri: str
) -> None:
    """Stored URIs cannot cross the configured bucket or prefix boundary."""
    monkeypatch.setattr(
        "data_platform.services.quarantine_storage._r2_client", lambda _: MagicMock()
    )
    store = R2QuarantineStore(_r2_settings())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="another bucket|configured prefix"):
        store._parse_uri(storage_uri)


def test_build_quarantine_store_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured factory selects R2 without leaking storage credentials."""
    monkeypatch.setattr(
        "data_platform.services.quarantine_storage._r2_client", lambda _: MagicMock()
    )

    assert isinstance(build_quarantine_store(_r2_settings()), R2QuarantineStore)  # type: ignore[arg-type]
