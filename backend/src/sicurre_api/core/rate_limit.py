from __future__ import annotations

import hashlib

from fastapi import Request
from slowapi import Limiter

from sicurre_api.core.security import extract_bearer_token


def get_rate_limit_key(request: Request) -> str:
    token = extract_bearer_token(request.headers.get("Authorization"))
    if token is not None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        return f"token:{token_hash}"

    client_host = request.client.host if request.client is not None else "anonymous"
    return f"ip:{client_host}"


limiter = Limiter(key_func=get_rate_limit_key, default_limits=[])
