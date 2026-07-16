from __future__ import annotations

import hashlib

from fastapi import Request
from slowapi import Limiter

from core.security import extract_bearer_token


def get_rate_limit_key(request: Request) -> str:
    token = extract_bearer_token(request.headers.get("Authorization"))
    if token is not None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        return f"token:{token_hash}"

    worker_secret = request.headers.get("X-Sicurre-Secret")
    if worker_secret:
        secret_hash = hashlib.sha256(worker_secret.encode("utf-8")).hexdigest()[:16]
        return f"worker:{secret_hash}"

    session_cookie = request.cookies.get("better-auth.session_token")
    if session_cookie:
        session_hash = hashlib.sha256(session_cookie.encode("utf-8")).hexdigest()[:16]
        return f"session:{session_hash}"

    client_host = request.headers.get("x-real-ip") or (
        request.client.host if request.client is not None else "anonymous"
    )
    return f"ip:{client_host}"


def touch_rate_limit_request(request: Request) -> None:
    _ = request.scope


limiter = Limiter(key_func=get_rate_limit_key, default_limits=["120/minute"])
