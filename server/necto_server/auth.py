"""Optional API-key authentication.

Auth is disabled by default (local development). Set NECTO_API_KEY to require an
X-API-Key header on every /v1 endpoint, including the live WebSocket.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from .config import settings


def check_api_key(provided: str | None) -> bool:
    """True when auth is disabled, or the provided key matches."""
    if not settings.api_key:
        return True
    if not provided:
        return False
    return secrets.compare_digest(provided, settings.api_key)


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not check_api_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
