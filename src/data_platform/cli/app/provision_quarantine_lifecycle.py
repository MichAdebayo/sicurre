"""Provision and verify the quarantine bucket's expiration lifecycle rule."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from core.config import Settings, get_settings
from data_platform.services.quarantine_storage import _r2_client

RULE_ID = "sicurre-quarantine-retention"


def desired_rule(settings: Settings) -> dict[str, Any]:
    """Return the managed R2 lifecycle rule for quarantine MIME objects."""
    return {
        "ID": RULE_ID,
        "Status": "Enabled",
        "Filter": {"Prefix": f"{settings.quarantine_r2_prefix.strip('/')}/"},
        "Expiration": {"Days": settings.quarantine_retention_days},
    }


def provision_lifecycle(settings: Settings) -> None:
    """Upsert the managed rule while preserving unrelated bucket lifecycle rules."""
    client = _r2_client(settings)
    bucket = str(settings.quarantine_r2_bucket_name)
    try:
        response = client.get_bucket_lifecycle_configuration(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NoSuchLifecycleConfiguration":
            raise
        response = {"Rules": []}
    rules = [rule for rule in response.get("Rules", []) if rule.get("ID") != RULE_ID]
    for rule in rules:
        if "Filter" not in rule and "Prefix" not in rule:
            rule["Prefix"] = ""
    rules.append(desired_rule(settings))
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={"Rules": rules},
    )
    configured = client.get_bucket_lifecycle_configuration(Bucket=bucket).get("Rules", [])
    if not any(
        rule.get("ID") == RULE_ID and rule.get("Status") == "Enabled" for rule in configured
    ):
        raise RuntimeError("Quarantine lifecycle rule verification failed")


def main() -> None:
    """Provision the configured production quarantine retention policy."""
    settings = get_settings()
    if settings.quarantine_storage_backend.strip().lower() != "r2":
        print("Quarantine lifecycle skipped: storage backend is not R2")
        return
    provision_lifecycle(settings)
    print(
        f"Quarantine lifecycle active: prefix={settings.quarantine_r2_prefix.strip('/')}/ "
        f"retention_days={settings.quarantine_retention_days}"
    )


if __name__ == "__main__":
    main()
