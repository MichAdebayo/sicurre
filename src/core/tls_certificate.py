"""Public TLS certificate inspection for Domain Shield.

Two paths report a certificate lifetime for a customer domain: the Domain
Shield refresh, and the Cloudflare auto-configuration write. Both take the
measurement from here so that neither has to invent one.
"""

from __future__ import annotations

import socket
import ssl
from datetime import datetime, timezone

_HANDSHAKE_TIMEOUT_SECONDS = 2.0

#: Returned when no certificate could be read. Callers record the domain as
#: uninspected; they must never substitute a lifetime of their own.
CERTIFICATE_UNAVAILABLE = -1


def get_ssl_expiry_days(domain: str) -> int:
    """Days remaining on the domain's public certificate.

    Returns ``CERTIFICATE_UNAVAILABLE`` when the host is unreachable, closes
    port 443, or presents a chain that does not verify — including a mail-only
    domain that serves no HTTPS at all, which is a legitimate configuration.
    """
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=_HANDSHAKE_TIMEOUT_SECONDS) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as secure_sock:
                certificate = secure_sock.getpeercert()
        expiry_text = (certificate or {}).get("notAfter")
        if not expiry_text:
            return CERTIFICATE_UNAVAILABLE
        # OpenSSL renders notAfter as e.g. "May 10 12:00:00 2026 GMT".
        expiry = datetime.strptime(str(expiry_text), "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc
        )
        return max(0, (expiry - datetime.now(timezone.utc)).days)
    except Exception:
        return CERTIFICATE_UNAVAILABLE
