"""Authenticated encryption for application-managed provider credentials."""

from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"
_LOCAL_KEY_CONTEXT = b"sicurre-local-secret-storage-v1"


def _key_bytes(configured_key: str | None, environment: str) -> bytes:
    """Resolve a 256-bit encryption key without exposing its source value."""
    if configured_key:
        try:
            padded_key = configured_key + "=" * (-len(configured_key) % 4)
            decoded = base64.urlsafe_b64decode(padded_key.encode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("SICURRE_SECRET_ENCRYPTION_KEY must be URL-safe base64") from exc
        if len(decoded) != 32:
            raise ValueError("SICURRE_SECRET_ENCRYPTION_KEY must decode to 32 bytes")
        return decoded
    if environment.lower() in {"production", "prod"}:
        raise ValueError("SICURRE_SECRET_ENCRYPTION_KEY is required in production")
    return hashlib.sha256(_LOCAL_KEY_CONTEXT).digest()


def encrypt_secret(value: str, *, configured_key: str | None, environment: str) -> str:
    """Encrypt a credential using AES-256-GCM and a random nonce."""
    if value.startswith(_PREFIX):
        return value
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key_bytes(configured_key, environment)).encrypt(
        nonce,
        value.encode("utf-8"),
        _PREFIX.encode("ascii"),
    )
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    result = f"{_PREFIX}{encoded}"
    # Postcondition, not decoration: decrypt_secret passes unprefixed values
    # through untouched for migration, so a regression that stopped encrypting
    # would store plaintext and read back cleanly with nothing to show for it.
    if not result.startswith(_PREFIX):  # pragma: no cover - defensive
        raise RuntimeError("encrypt_secret produced an unencrypted value")
    return result


def decrypt_secret(value: str, *, configured_key: str | None, environment: str) -> str:
    """Decrypt a credential; accept legacy plaintext only for migration."""
    if not value.startswith(_PREFIX):
        # Legacy plaintext, accepted so existing rows keep working. Say so:
        # silence here is what would let a stopped-encrypting regression pass
        # for a working system.
        logger.warning(
            "Reading a credential that is not encrypted; re-save it to encrypt at rest"
        )
        return value
    payload = base64.urlsafe_b64decode(value.removeprefix(_PREFIX).encode("ascii"))
    if len(payload) < 29:
        raise ValueError("Encrypted secret payload is invalid")
    return AESGCM(_key_bytes(configured_key, environment)).decrypt(
        payload[:12],
        payload[12:],
        _PREFIX.encode("ascii"),
    ).decode("utf-8")
