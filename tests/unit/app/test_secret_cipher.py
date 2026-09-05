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


@pytest.mark.parametrize("invalid_key", ["not-ASCII-£", "dG9vLXNob3J0"])
def test_invalid_configured_keys_are_rejected(invalid_key: str) -> None:
    """Reject malformed or incorrectly sized production encryption keys."""
    with pytest.raises(ValueError, match="SICURRE_SECRET_ENCRYPTION_KEY"):
        encrypt_secret("token", configured_key=invalid_key, environment="production")


def test_truncated_encrypted_payload_is_rejected() -> None:
    """Reject ciphertext that cannot contain a nonce and authentication tag."""
    truncated = "enc:v1:" + base64.urlsafe_b64encode(b"short").decode("ascii")

    with pytest.raises(ValueError, match="payload is invalid"):
        decrypt_secret(truncated, configured_key=TEST_KEY, environment="production")


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


def test_encrypting_always_yields_a_marked_ciphertext() -> None:
    """The prefix is what tells a stored value apart from plaintext.

    decrypt_secret passes an unprefixed value through untouched so existing
    rows keep working, which means a regression that stopped encrypting would
    store plaintext and read back cleanly. The postcondition is the only place
    that failure can be caught at the point it happens.
    """
    for secret in ("token", "", "a" * 4096, "clé-avec-accents"):
        assert encrypt_secret(
            secret, configured_key=TEST_KEY, environment="production"
        ).startswith("enc:v1:")


def test_reading_legacy_plaintext_is_reported(caplog: pytest.LogCaptureFixture) -> None:
    """Accepting it silently is what would hide a stopped-encrypting regression."""
    with caplog.at_level("WARNING"):
        assert (
            decrypt_secret("plain-token", configured_key=TEST_KEY, environment="production")
            == "plain-token"
        )
    assert any("not encrypted" in r.message for r in caplog.records)


def test_reading_a_real_ciphertext_stays_quiet(caplog: pytest.LogCaptureFixture) -> None:
    """The warning must mark the exception, not every read."""
    sealed = encrypt_secret("token", configured_key=TEST_KEY, environment="production")
    with caplog.at_level("WARNING"):
        assert decrypt_secret(sealed, configured_key=TEST_KEY, environment="production") == "token"
    assert not [r for r in caplog.records if "not encrypted" in r.message]
