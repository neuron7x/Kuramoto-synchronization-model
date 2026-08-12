# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Middleware components for the cortex service."""

from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .logger import get_logger

logger = get_logger(__name__)

# Context variable to store request ID for the current request
request_id_context: ContextVar[str] = ContextVar("request_id", default="")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that adds request ID tracking to all requests."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:  # type: ignore[override]
        """Process request with request ID tracking.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            HTTP response with X-Request-ID header
        """
        # Get or generate request ID
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        request_id_context.set(request_id)

        # Add request ID to request state for easy access
        request.state.request_id = request_id

        # Process request
        start_time = time.perf_counter()
        response: Response = await call_next(request)  # type: ignore[misc]
        duration = time.perf_counter() - start_time

        # Add request ID to response headers
        response.headers[REQUEST_ID_HEADER] = request_id

        # Log request completion
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_seconds": round(duration, 4),
            },
        )

        return response


def get_request_id() -> str:
    """Get the current request ID from context.

    Returns:
        Current request ID, or empty string if not in request context
    """
    return request_id_context.get()


__all__ = ["RequestIDMiddleware", "get_request_id", "REQUEST_ID_HEADER"]
