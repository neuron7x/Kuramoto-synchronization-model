"""
Minimal security helpers for FastAPI endpoints: API key check + rate limiting.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

# Basic rate limiting: 60 req/min per client IP
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def _ct_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def api_key_guard(header_name: str = "X-THERMO-KEY"):
    """Dependency to protect thermo endpoints via static API key."""

    async def _check(req: Request):
        expected: Optional[str] = os.getenv("THERMO_API_KEY")
        if not expected:
            # Lock down by default when not configured.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="THERMO_API_KEY is not configured",
            )
        received = req.headers.get(header_name)
        if not received or not _ct_equal(received, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
            )
        return True

    return _check
