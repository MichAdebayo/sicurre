from __future__ import annotations

from core.config import Settings
from data_platform.services.shared import snapshot_storage as module


def test_resolve_snapshot_storage_backend_uses_source_override() -> None:
    settings = Settings(
        _env_file=None,
        raw_snapshot_storage_backend="r2",
        phishtank_snapshot_storage_backend="local",
        database_historical_snapshot_storage_backend="local",
    )

    assert settings.resolve_snapshot_storage_backend(source_key="phishtank") == "local"
    assert (
        settings.resolve_snapshot_storage_backend(source_key="database-historical")
        == "local"
    )
    assert settings.resolve_snapshot_storage_backend(source_key="sap_labs") == "r2"


def test_build_snapshot_store_prefers_source_backend_override(
    monkeypatch, tmp_path
) -> None:
    settings = Settings(
        _env_file=None,
        raw_snapshot_storage_backend="r2",
        phishtank_snapshot_storage_backend="local",
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    store = module.build_snapshot_store(
        local_root_dir=tmp_path,
        repo_root=tmp_path,
        source_key="phishtank",
    )

    assert isinstance(store, module.LocalSnapshotStore)


def test_build_snapshot_store_uses_global_backend_without_source_override(
    monkeypatch, tmp_path
) -> None:
    settings = Settings(
        _env_file=None,
        raw_snapshot_storage_backend="r2",
        raw_snapshot_r2_bucket_name="sicurre-raw",
        raw_snapshot_r2_endpoint_url="https://example.com",
        raw_snapshot_r2_access_key_id="key-id",
        raw_snapshot_r2_secret_access_key="secret",
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    store = module.build_snapshot_store(
        local_root_dir=tmp_path,
        repo_root=tmp_path,
        source_key="common_crawl",
    )

    assert isinstance(store, module.R2SnapshotStore)
    assert store.root_prefix == settings.raw_snapshot_prefix
