"""Platform administrator allowlist utility tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[3] / "scripts" / "app" / "manage-platform-admin.py"
SPEC = importlib.util.spec_from_file_location("manage_platform_admin", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_grant_and_revoke_are_idempotent() -> None:
    """Repeated role operations produce no duplicate or unrelated env changes."""
    original = "SICURRE_ENVIRONMENT=production\nSICURRE_PLATFORM_ADMIN_EMAILS=first@example.test\n"

    granted, changed = MODULE.update_admin_allowlist(
        original,
        email="OWNER@EXAMPLE.TEST",
        action="grant",
    )
    assert changed is True
    assert "first@example.test,owner@example.test" in granted

    unchanged, changed_again = MODULE.update_admin_allowlist(
        granted,
        email="owner@example.test",
        action="grant",
    )
    assert changed_again is False
    assert unchanged == granted

    revoked, changed_revoke = MODULE.update_admin_allowlist(
        granted,
        email="first@example.test",
        action="revoke",
    )
    assert changed_revoke is True
    assert "SICURRE_PLATFORM_ADMIN_EMAILS=owner@example.test" in revoked


def test_invalid_email_is_rejected() -> None:
    """Malformed identifiers cannot be written to the production allowlist."""
    with pytest.raises(ValueError, match="valid admin email"):
        MODULE.update_admin_allowlist("", email="not-an-email", action="grant")
