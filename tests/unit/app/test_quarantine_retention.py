"""Tests for operational quarantine expiry and R2 lifecycle enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from data_platform.cli.app import provision_quarantine_lifecycle as lifecycle_module
from data_platform.cli.app.provision_quarantine_lifecycle import (
    RULE_ID,
    desired_rule,
    provision_lifecycle,
)
from data_platform.cron_schedulers.app import run_quarantine_purge as purge_runner
from data_platform.services.quarantine_retention import (
    QuarantinePurgeResult,
    purge_expired_quarantine,
)


@pytest.mark.asyncio
async def test_purge_deletes_mime_and_scrubs_expired_item() -> None:
    """Successful custody deletion leaves only a non-content audit tombstone."""
    calls: list[tuple[str, tuple[object, ...]]] = []
    deleted: list[str] = []

    async def query(sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        calls.append((sql, params))
        if sql.startswith("SELECT"):
            return [
                {
                    "id": "item-1",
                    "workspace_id": "workspace-1",
                    "raw_storage_uri": "r2://bucket/quarantine/workspace-1/item-1.eml",
                }
            ]
        return [{"id": "item-1"}]

    class Store:
        async def delete(self, uri: str) -> None:
            deleted.append(uri)

    result = await purge_expired_quarantine(
        query=query,
        store=Store(),
        workspace_id="workspace-1",
        now=datetime(2026, 8, 9, tzinfo=UTC),
    )

    assert (result.candidates, result.purged, result.failed) == (1, 1, 0)
    assert deleted == ["r2://bucket/quarantine/workspace-1/item-1.eml"]
    assert "workspace_id = ?" in calls[0][0]
    assert "sender = '[deleted]'" in calls[1][0]
    assert "body_text = ''" in calls[1][0]


@pytest.mark.asyncio
async def test_purge_preserves_failed_item_for_retry() -> None:
    """A failed object deletion cannot be recorded as successful DB purging."""
    calls: list[str] = []

    async def query(sql: str, _params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        calls.append(sql)
        return [
            {
                "id": "item-1",
                "workspace_id": "workspace-1",
                "raw_storage_uri": "r2://bucket/quarantine/workspace-1/item-1.eml",
            }
        ]

    class Store:
        async def delete(self, _uri: str) -> None:
            raise RuntimeError("R2 unavailable")

    result = await purge_expired_quarantine(
        query=query,
        store=Store(),
    )

    assert (result.candidates, result.purged, result.failed) == (1, 0, 1)
    assert len(calls) == 1


def test_desired_lifecycle_matches_quarantine_retention() -> None:
    """The bucket and application use one retention duration and prefix."""
    settings = SimpleNamespace(quarantine_r2_prefix="quarantine", quarantine_retention_days=14)

    assert desired_rule(settings) == {  # type: ignore[arg-type]
        "ID": RULE_ID,
        "Status": "Enabled",
        "Filter": {"Prefix": "quarantine/"},
        "Expiration": {"Days": 14},
    }


def test_lifecycle_upsert_preserves_unrelated_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provisioning replaces only Sicurre's managed lifecycle rule."""
    existing = {
        "ID": "Default Multipart Abort Rule",
        "Status": "Enabled",
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
    }
    client = MagicMock()
    client.get_bucket_lifecycle_configuration.side_effect = [
        {"Rules": [existing]},
        {"Rules": [{"ID": RULE_ID, "Status": "Enabled"}]},
    ]
    monkeypatch.setattr(
        "data_platform.cli.app.provision_quarantine_lifecycle._r2_client",
        lambda _settings: client,
    )
    settings = SimpleNamespace(
        quarantine_r2_bucket_name="sicurre-quarantine",
        quarantine_r2_prefix="quarantine",
        quarantine_retention_days=14,
    )

    provision_lifecycle(settings)  # type: ignore[arg-type]

    rules = client.put_bucket_lifecycle_configuration.call_args.kwargs["LifecycleConfiguration"][
        "Rules"
    ]
    assert rules[0]["ID"] == "Default Multipart Abort Rule"
    assert rules[0]["Prefix"] == ""
    assert rules[1] == desired_rule(settings)  # type: ignore[arg-type]


def test_lifecycle_handles_bucket_without_existing_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bucket without lifecycle configuration receives the managed rule."""
    client = MagicMock()
    client.get_bucket_lifecycle_configuration.side_effect = [
        ClientError(
            {"Error": {"Code": "NoSuchLifecycleConfiguration"}},
            "GetBucketLifecycleConfiguration",
        ),
        {"Rules": [{"ID": RULE_ID, "Status": "Enabled"}]},
    ]
    monkeypatch.setattr(lifecycle_module, "_r2_client", lambda _settings: client)
    settings = SimpleNamespace(
        quarantine_r2_bucket_name="sicurre-quarantine",
        quarantine_r2_prefix="quarantine",
        quarantine_retention_days=14,
    )

    provision_lifecycle(settings)  # type: ignore[arg-type]

    rules = client.put_bucket_lifecycle_configuration.call_args.kwargs["LifecycleConfiguration"][
        "Rules"
    ]
    assert rules == [desired_rule(settings)]  # type: ignore[arg-type]


def test_lifecycle_rejects_unverified_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployment fails if R2 does not return the enabled managed rule."""
    client = MagicMock()
    client.get_bucket_lifecycle_configuration.side_effect = [
        {"Rules": []},
        {"Rules": []},
    ]
    monkeypatch.setattr(lifecycle_module, "_r2_client", lambda _settings: client)
    settings = SimpleNamespace(
        quarantine_r2_bucket_name="sicurre-quarantine",
        quarantine_r2_prefix="quarantine",
        quarantine_retention_days=14,
    )

    with pytest.raises(RuntimeError, match="verification failed"):
        provision_lifecycle(settings)  # type: ignore[arg-type]


def test_lifecycle_main_skips_local_storage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Local development does not attempt to configure an R2 bucket."""
    monkeypatch.setattr(
        lifecycle_module,
        "get_settings",
        lambda: SimpleNamespace(quarantine_storage_backend="local"),
    )

    lifecycle_module.main()

    assert "storage backend is not R2" in capsys.readouterr().out


def test_lifecycle_main_provisions_r2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R2 startup provisions and reports the effective retention contract."""
    settings = SimpleNamespace(
        quarantine_storage_backend="r2",
        quarantine_r2_prefix="quarantine",
        quarantine_retention_days=14,
    )
    provisioned: list[object] = []
    monkeypatch.setattr(lifecycle_module, "get_settings", lambda: settings)
    monkeypatch.setattr(lifecycle_module, "provision_lifecycle", provisioned.append)

    lifecycle_module.main()

    assert provisioned == [settings]
    assert "retention_days=14" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_daily_purge_runner_reports_storage_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scheduled job exits unsuccessfully so failed deletions remain observable."""

    async def purge(**_kwargs: object) -> QuarantinePurgeResult:
        return QuarantinePurgeResult(candidates=1, purged=0, failed=1)

    monkeypatch.setattr(purge_runner, "get_settings", lambda: object())
    monkeypatch.setattr(purge_runner, "build_quarantine_store", lambda _settings: object())
    monkeypatch.setattr(purge_runner, "purge_expired_quarantine", purge)

    with pytest.raises(RuntimeError, match="Failed to purge 1"):
        await purge_runner.main()


@pytest.mark.asyncio
async def test_daily_purge_runner_accepts_complete_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scheduled job succeeds when all custody objects are purged."""

    async def purge(**_kwargs: object) -> QuarantinePurgeResult:
        return QuarantinePurgeResult(candidates=2, purged=2, failed=0)

    monkeypatch.setattr(purge_runner, "get_settings", lambda: object())
    monkeypatch.setattr(purge_runner, "build_quarantine_store", lambda _settings: object())
    monkeypatch.setattr(purge_runner, "purge_expired_quarantine", purge)

    await purge_runner.main()
