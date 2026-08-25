"""Loopback-only fault gateway for the local certification POC."""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import urlsplit

import httpx

from poc.inference import FaultScenario


class PocFaultGateway:
    """Proxy local inference while supporting reversible bounded failures."""

    def __init__(self, upstream_classify_url: str, *, fault_ttl_seconds: float = 120.0) -> None:
        self._upstream_classify_url = upstream_classify_url
        self._upstream_health_url = upstream_classify_url.removesuffix("/v1/classify") + "/health"
        self._fault_ttl_seconds = fault_ttl_seconds
        self._scenario: FaultScenario | None = None
        self._fault_expires_at = 0.0
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def classify_url(self) -> str:
        """Return the started gateway's local classify URL."""
        if self._server is None:
            raise RuntimeError("Fault gateway is not started.")
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1/classify"

    @property
    def active_scenario(self) -> FaultScenario | None:
        """Return the active fault, restoring nominal mode after its TTL."""
        with self._lock:
            if self._scenario is not None and time.monotonic() >= self._fault_expires_at:
                self._scenario = None
            return self._scenario

    def start(self) -> PocFaultGateway:
        """Start the loopback proxy once and return this gateway."""
        if self._server is not None:
            return self
        gateway = self

        class GatewayHandler(BaseHTTPRequestHandler):
            gateway_ref: ClassVar[PocFaultGateway] = gateway

            def do_GET(self) -> None:  # noqa: N802
                self.gateway_ref._handle(self, "GET")

            def do_POST(self) -> None:  # noqa: N802
                self.gateway_ref._handle(self, "POST")

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), GatewayHandler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="sicurre-poc-fault-gateway",
            daemon=True,
        )
        self._thread.start()
        return self

    def inject(self, scenario: FaultScenario) -> None:
        """Activate one bounded fault until explicit or automatic restoration."""
        with self._lock:
            self._scenario = scenario
            self._fault_expires_at = time.monotonic() + self._fault_ttl_seconds

    def restore(self) -> None:
        """Restore nominal proxy behavior immediately."""
        with self._lock:
            self._scenario = None
            self._fault_expires_at = 0.0

    def close(self) -> None:
        """Stop the local proxy when explicitly requested by tests or tooling."""
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def _handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        scenario = self.active_scenario
        if handler.path not in {"/health", "/v1/classify"}:
            self._write(handler, 404, b'{"detail":"Not found"}')
            return
        if scenario is FaultScenario.SERVICE_UNAVAILABLE:
            self._write(handler, 503, b'{"detail":"Injected inference outage"}')
            return
        if handler.path == "/v1/classify" and scenario is FaultScenario.INVALID_CONTRACT:
            self._write(handler, 200, b'{"unexpected":true}')
            return

        body = b""
        if method == "POST":
            content_length = min(int(handler.headers.get("Content-Length", "0")), 65536)
            body = handler.rfile.read(content_length)
        headers = {
            "Content-Type": handler.headers.get("Content-Type", "application/json"),
            "Authorization": handler.headers.get("Authorization", ""),
        }
        if handler.path == "/v1/classify" and scenario is FaultScenario.INVALID_BEARER:
            headers["Authorization"] = "Bearer sicurre-poc-injected-invalid-key"
        upstream_url = (
            self._upstream_health_url if handler.path == "/health" else self._upstream_classify_url
        )
        try:
            response = httpx.request(
                method,
                upstream_url,
                content=body or None,
                headers=headers,
                timeout=35.0,
            )
        except httpx.HTTPError:
            self._write(handler, 502, b'{"detail":"Upstream inference unavailable"}')
            return
        self._write(
            handler,
            response.status_code,
            response.content,
            response.headers.get("content-type", "application/json"),
        )

    @staticmethod
    def _write(
        handler: BaseHTTPRequestHandler,
        status_code: int,
        payload: bytes,
        content_type: str = "application/json",
    ) -> None:
        handler.send_response(status_code)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)


def gateway_settings_url(gateway: PocFaultGateway) -> str:
    """Validate and return the loopback classify URL used by copied settings."""
    parsed = urlsplit(gateway.classify_url)
    if parsed.hostname != "127.0.0.1":
        raise RuntimeError("POC fault gateway must remain loopback-only.")
    return gateway.classify_url
