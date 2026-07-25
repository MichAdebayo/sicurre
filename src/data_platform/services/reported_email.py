"""Workspace aliasing, sanitization, and private storage for missed threats."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from core.config import Settings

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){8,15}(?!\d)")


class InvalidReportAlias(ValueError):
    """Raised when an alias is malformed or its signature is invalid."""


class ReportAliasCodec:
    """Create compact signed aliases without persisting a bearer token."""

    def __init__(self, secret: str) -> None:
        if len(secret.encode()) < 32:
            raise ValueError("SICURRE_REPORTED_EMAIL_ALIAS_SECRET must contain at least 32 bytes")
        self.secret = secret.encode()

    def encode(self, workspace_id: str) -> str:
        """Encode a UUID workspace identifier into a signed opaque token."""
        payload = uuid.UUID(workspace_id).bytes
        signature = hmac.digest(self.secret, payload, "sha256")[:16]
        return f"{_b64(payload)}.{_b64(signature)}"

    def decode(self, token: str) -> str:
        """Verify an alias token and return its workspace identifier."""
        try:
            payload_text, signature_text = token.split(".", 1)
            payload = _unb64(payload_text)
            signature = _unb64(signature_text)
            expected = hmac.digest(self.secret, payload, "sha256")[:16]
            if len(payload) != 16 or not hmac.compare_digest(signature, expected):
                raise InvalidReportAlias("Invalid report alias")
            return str(uuid.UUID(bytes=payload))
        except (ValueError, TypeError) as exc:
            raise InvalidReportAlias("Invalid report alias") from exc


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def report_address(base_address: str, token: str) -> str:
    """Insert the workspace token into a configured report mailbox."""
    local, domain = base_address.strip().lower().split("@", 1)
    return f"{local}+{token}@{domain}"


def sanitized_evidence(raw_message: bytes) -> bytes:
    """Discard the forwarding envelope and retain an anonymized evidence record."""
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    original = next(
        (
            part.get_payload(0)
            for part in message.walk()
            if part.get_content_type() == "message/rfc822" and part.get_payload()
        ),
        message,
    )
    body = _message_text(original)
    evidence = {
        "schema_version": "reported-email-v1",
        "subject": _redact(str(original.get("subject", ""))),
        "body": _redact(body),
    }
    return json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()


def _message_text(message: Any) -> str:
    if message.is_multipart():
        plain = [
            part.get_content()
            for part in message.walk()
            if part.get_content_type() == "text/plain"
            and part.get_content_disposition() != "attachment"
        ]
        return "\n".join(str(value) for value in plain)
    try:
        return str(message.get_content())
    except (AttributeError, LookupError, UnicodeError):
        payload = message.get_payload(decode=True) or b""
        return payload.decode(errors="replace")


def _redact(value: str) -> str:
    return PHONE_PATTERN.sub("[PHONE]", EMAIL_PATTERN.sub("[EMAIL]", value)).strip()


@dataclass(frozen=True, slots=True)
class ReportedEmailObject:
    storage_uri: str
    content_hash: str
    size_bytes: int


class ReportedEmailStore(Protocol):
    async def write(
        self, *, workspace_id: str, report_id: str, payload: bytes
    ) -> ReportedEmailObject: ...


class LocalReportedEmailStore:
    """Local private evidence storage for development."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def write(
        self, *, workspace_id: str, report_id: str, payload: bytes
    ) -> ReportedEmailObject:
        path = (self.root / workspace_id / f"{report_id}.json").resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Reported-email path escapes its storage root")
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True, mode=0o700)
        await asyncio.to_thread(path.write_bytes, payload)
        await asyncio.to_thread(path.chmod, 0o600)
        return _object(f"file://{path}", payload)


class R2ReportedEmailStore:
    """Dedicated private R2 storage for sanitized false-negative evidence."""

    def __init__(self, settings: Settings) -> None:
        values = (
            settings.reported_email_r2_bucket_name,
            settings.reported_email_r2_endpoint_url,
            settings.reported_email_r2_access_key_id,
            settings.reported_email_r2_secret_access_key,
        )
        if not all(values):
            raise RuntimeError("Reported-email R2 credentials are incomplete")
        self.bucket = str(settings.reported_email_r2_bucket_name)
        self.prefix = settings.reported_email_r2_prefix.strip("/")
        endpoint = str(settings.reported_email_r2_endpoint_url).rstrip("/")
        suffix = f"/{self.bucket}"
        if endpoint.endswith(suffix):
            endpoint = endpoint[: -len(suffix)]
        import boto3

        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.reported_email_r2_access_key_id,
            aws_secret_access_key=settings.reported_email_r2_secret_access_key,
            region_name=settings.reported_email_r2_region,
        )

    async def write(
        self, *, workspace_id: str, report_id: str, payload: bytes
    ) -> ReportedEmailObject:
        key = PurePosixPath(self.prefix, workspace_id, f"{report_id}.json").as_posix()
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        return _object(f"r2://{self.bucket}/{key}", payload)


def _object(uri: str, payload: bytes) -> ReportedEmailObject:
    return ReportedEmailObject(
        storage_uri=uri,
        content_hash=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def build_reported_email_store(settings: Settings) -> ReportedEmailStore:
    """Resolve the configured reported-email evidence backend."""
    backend = settings.reported_email_storage_backend.strip().lower()
    if backend == "local":
        return LocalReportedEmailStore(settings.reported_email_local_dir)
    if backend == "r2":
        return R2ReportedEmailStore(settings)
    raise RuntimeError("SICURRE_REPORTED_EMAIL_STORAGE_BACKEND must be local or r2")
