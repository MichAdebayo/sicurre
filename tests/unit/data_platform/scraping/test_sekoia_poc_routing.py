"""Tests for production and POC SEKOIA snapshot routing."""

import pytest

from data_platform.cron_schedulers.scraping.run_sekoia_ioc import (
    configure_snapshot_environment,
)


def test_default_cron_uses_production_namespace() -> None:
    environ: dict[str, str] = {}
    configure_snapshot_environment(environ, reserved=False)
    assert environ["SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND"] == "prod"
    assert environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] == "cron/scraping/sekoia_ioc"


def test_reserved_cron_uses_reserved_namespace() -> None:
    environ: dict[str, str] = {}
    configure_snapshot_environment(environ, reserved=True)
    assert environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] == "cron/reserved/scraping/sekoia_ioc"


def test_poc_cron_requires_explicit_external_write_approval() -> None:
    with pytest.raises(RuntimeError, match="explicit sandbox"):
        configure_snapshot_environment({"SICURRE_POC_MODE": "true"}, reserved=False)


def test_poc_cron_uses_demonstration_namespace() -> None:
    environ = {
        "SICURRE_POC_MODE": "true",
        "SICURRE_POC_ALLOW_EXTERNAL_WRITES": "true",
        "SICURRE_POC_R2_PREFIX": "demonstrations/jury",
    }
    configure_snapshot_environment(environ, reserved=False)
    assert environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] == "demonstrations/jury/scraping/sekoia_ioc"
