"""One long-lived HTTP client for the inference service.

The scan handler previously opened `httpx.AsyncClient` per request. Each open
built a fresh connection pool and paid a TLS handshake to the inference host
before a single byte of the classification request went out. Measurement put
the data platform's `inference` stage at ~1852 ms against the inference
service's own reported total of ~1577 ms — roughly 275 ms of the scan spent
establishing a connection that the previous scan had already established and
then discarded.

Keeping one client alive lets keep-alive do its job: the TCP and TLS setup is
paid once per process rather than once per email.

The client is closed from the application lifespan so the pool does not outlive
the event loop it was created on.
"""

from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None

# Matches the previous per-request timeout so this change alters connection
# reuse only, never how long a slow provider is tolerated.
_TIMEOUT = httpx.Timeout(15.0)

# Small pool: the scan path issues one request at a time per worker, and a
# bounded pool keeps a stalled inference host from accumulating sockets.
_LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=5)


def get_inference_client() -> httpx.AsyncClient:
    """Return the process-wide inference client, creating it on first use."""
    global _client
    # getattr rather than attribute access: anything cached here that does not
    # look like a live client is discarded and rebuilt, so a half-initialised or
    # substituted object cannot be handed to the scan path.
    if _client is None or getattr(_client, "is_closed", True):
        _client = httpx.AsyncClient(timeout=_TIMEOUT, limits=_LIMITS)
    return _client


async def close_inference_client() -> None:
    """Close the shared client. Safe to call when one was never created."""
    global _client
    client, _client = _client, None
    if client is not None and not getattr(client, "is_closed", True):
        await client.aclose()
