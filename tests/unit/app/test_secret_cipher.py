"""Credential encryption contract tests."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import ValidationError

from core.config import Settings
from core.secret_cipher import decrypt_secret, encrypt_secret

TEST_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")


def test_secret_round_trip_uses_random_authenticated_ciphertext() -> None:
    """Equal credentials encrypt differently and decrypt without data loss."""
    first = encrypt_secret("cloudflare-token", configured_key=TEST_KEY, environment="test")
    second = encrypt_secret("cloudflare-token", configured_key=TEST_KEY, environment="test")

    assert first.startswith("enc:v1:")
    assert first != second
    assert "cloudflare-token" not in first
    assert decrypt_secret(first, configured_key=TEST_KEY, environment="test") == "cloudflare-token"


def test_unpadded_urlsafe_key_round_trip() -> None:
    """Accept the unpadded key format documented for production operators."""
    key = TEST_KEY.rstrip("=")
    encrypted = encrypt_secret("cloudflare-token", configured_key=key, environment="production")

    assert decrypt_secret(encrypted, configured_key=key, environment="production") == "cloudflare-token"


def test_legacy_plaintext_is_readable_only_for_migration() -> None:
    """Existing rows remain operable until rewritten through the encrypted path."""
    assert (
        decrypt_secret("legacy-token", configured_key=TEST_KEY, environment="test")
        == "legacy-token"
    )


def test_wrong_key_cannot_decrypt_ciphertext() -> None:
    """AES-GCM authentication rejects the wrong application key."""
    encrypted = encrypt_secret("token", configured_key=TEST_KEY, environment="test")
    wrong_key = base64.urlsafe_b64encode(b"x" * 32).decode("ascii")

    with pytest.raises(InvalidTag):
        decrypt_secret(encrypted, configured_key=wrong_key, environment="test")


def test_production_settings_require_valid_secret_key() -> None:
    """Production cannot start with plaintext provider credential storage."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", secret_encryption_key=None)

    settings = Settings(
        _env_file=None,
        environment="production",
        secret_encryption_key=TEST_KEY,
    )
    assert settings.secret_encryption_key == TEST_KEY
