# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Request-deadline middleware emitting a canonical 504 envelope.

Before this middleware a handler that exceeded its time budget surfaced
as an *unhandled exception* → HTTP 500 via the catch-all handler. That
conflated two operationally distinct UX states: a genuine server fault
(``server_error``) and a deadline breach (``timeout``). IERD-Q5 §5
requires the six UX states to be individually distinguishable by the
frontend; ``timeout`` was the only one the API could not emit.

``RequestTimeoutMiddleware`` wraps the downstream call in
``asyncio.wait_for`` with a configured deadline and, on expiry, returns
``504 Gateway Timeout`` wrapped in the standard ``ErrorResponse``
envelope (``{error: {code, message, path, meta}}``) — the same shape
every other 4xx/5xx uses, so the frontend renders the timeout state
through one path.

Streaming/long-lived routes (the websocket stream) must not be bounded
by a single request deadline; they are exempt by path prefix.
WebSocket connections bypass ``BaseHTTPMiddleware`` entirely, so the
prefix guard is belt-and-braces for any future SSE route.

Tracks claim ``ux-readiness-state-coverage`` and invariant
``INV-API-CONTRACT`` (the OpenAPI contract now declares 504 on every
operation via ``COMMON_ERROR_RESPONSES`` and the app emits it).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from application.api.errors import ApiErrorCode, build_error_envelope

LOGGER: Final = logging.getLogger("geosync.api.timeout")

# Generous default: high enough that no nominal request is affected, low
# enough that a wedged handler cannot pin a worker indefinitely. Override
# via the GEOSYNC_REQUEST_TIMEOUT_SECONDS env var (resolved by the app
# factory, not read here, so this module stays import-pure and testable).
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0

# Paths whose responses are intentionally long-lived; a single
# request-scoped deadline is semantically wrong for them.
_DEFAULT_EXEMPT_PREFIXES: Final[tuple[str, ...]] = ("/ws",)


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Bound every non-streaming request by a wall-clock deadline.

    On ``asyncio.TimeoutError`` the in-flight handler task is cancelled
    by ``asyncio.wait_for`` and a canonical ``504`` envelope is
    returned. The deadline must be strictly positive; a non-positive
    value is a contract violation and fails closed at construction.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        exempt_path_prefixes: tuple[str, ...] = _DEFAULT_EXEMPT_PREFIXES,
    ) -> None:
        super().__init__(app)
        if not timeout_seconds > 0.0:
            raise ValueError(
                "RequestTimeoutMiddleware timeout_seconds must be > 0; "
                f"got {timeout_seconds!r}. Fail-closed: a non-positive "
                f"deadline would reject every request as timed-out."
            )
        self._timeout_seconds = float(timeout_seconds)
        self._exempt_path_prefixes = tuple(exempt_path_prefixes)

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self._exempt_path_prefixes)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if self._is_exempt(request.url.path):
            return await call_next(request)
        try:
            return await asyncio.wait_for(call_next(request), timeout=self._timeout_seconds)
        except (asyncio.TimeoutError, TimeoutError):
            LOGGER.warning(
                "Request exceeded the %.3fs deadline; returning 504",
                self._timeout_seconds,
                extra={"path": request.url.path},
            )
            return build_error_envelope(
                status_code=504,
                code=ApiErrorCode.GATEWAY_TIMEOUT,
                message=(
                    "The request exceeded the server processing deadline "
                    f"of {self._timeout_seconds:g}s."
                ),
                path=request.url.path,
                meta={"timeout_seconds": self._timeout_seconds},
            )
