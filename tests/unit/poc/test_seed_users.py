"""Tests for the local POC user-seeding command."""

import pytest

from poc import seed_users


def test_seed_command_reports_roles_without_passwords(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(seed_users, "ensure_local_auth_db", lambda: calls.append("seeded"))
    monkeypatch.setattr(seed_users, "POC_AUTH_DB_PATH", "/tmp/poc.db")
    monkeypatch.setattr(
        seed_users,
        "demo_accounts",
        lambda: [
            {"role": "Administrateur", "email": "admin@example.test"},
            {"role": "Observateur", "email": "viewer@example.test"},
        ],
    )

    seed_users.main()

    output = capsys.readouterr().out
    assert calls == ["seeded"]
    assert "admin@example.test" in output
    assert "viewer@example.test" in output
    assert "password" not in output.lower()
