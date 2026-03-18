from __future__ import annotations

from sicurre_api.core.config import Settings


def test_dev_tokens_allowed_in_dev_by_default() -> None:
    settings = Settings(environment="dev")

    assert settings.allow_dev_tokens is True


def test_dev_tokens_disabled_in_prod_by_default() -> None:
    settings = Settings(environment="prod")

    assert settings.allow_dev_tokens is False


def test_explicit_dev_token_override_wins() -> None:
    settings = Settings(environment="prod", auth_allow_dev_tokens=True)

    assert settings.allow_dev_tokens is True
