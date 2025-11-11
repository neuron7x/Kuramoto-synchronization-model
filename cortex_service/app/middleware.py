"""Middleware components for request processing.

This module provides middleware for request ID tracking, structured logging
context enrichment, and optional rate limiting hooks.
"""

from __future__ import annotations

import contextvars
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Context variable for storing the current request ID
request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that ensures every request has a unique request ID.
    
    The request ID is extracted from the X-Request-ID header if present,
    or generated as a new UUID if absent. The request ID is:
    - Stored in a context variable for access throughout the request
    - Added to the response headers
    - Available for structured logging
    
    Attributes:
        header_name: Name of the header to use (default: X-Request-ID)
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        """Initialize the middleware.
        
        Args:
            app: The ASGI application
            header_name: Name of the request ID header
        """
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request and inject request ID.
        
        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler
            
        Returns:
            Response with X-Request-ID header added
        """
        # Extract or generate request ID
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in context variable
        request_id_context.set(request_id)
        
        # Process request
        response: Response = await call_next(request)
        
        # Add to response headers
        response.headers[self.header_name] = request_id
        
        return response


def get_request_id() -> str | None:
    """Get the current request ID from context.
    
    Returns:
        The current request ID, or None if not in a request context
    """
    return request_id_context.get()


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Middleware that enriches logs with request context.
    
    This middleware adds structured logging context including:
    - Request ID
    - Endpoint path and method
    - Request duration
    - Response status code
    
    Log messages within the request context will automatically include
    these fields when using structured logging.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware.
        
        Args:
            app: The ASGI application
        """
        super().__init__(app)
        self.logger = logging.getLogger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request with logging context.
        
        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler
            
        Returns:
            Response from the next handler
        """
        start_time = time.perf_counter()
        request_id = get_request_id() or "unknown"
        
        # Log request start
        self.logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_host": request.client.host if request.client else None,
            },
        )
        
        # Process request
        try:
            response: Response = await call_next(request)
            duration = time.perf_counter() - start_time
            
            # Log request completion
            self.logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_seconds": duration,
                },
            )
            
            return response
        except Exception as exc:
            duration = time.perf_counter() - start_time
            
            # Log request failure
            self.logger.error(
                "Request failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_seconds": duration,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Placeholder middleware for rate limiting.
    
    This middleware provides hooks for integrating rate limiting logic.
    In production, this could be connected to Redis or an in-memory store
    to track request rates per client.
    
    Note:
        This is a placeholder implementation that does not enforce limits.
        It serves as an integration point for future rate limiting logic.
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = False,
        requests_per_minute: int = 100,
    ) -> None:
        """Initialize the middleware.
        
        Args:
            app: The ASGI application
            enabled: Whether rate limiting is enabled
            requests_per_minute: Maximum requests allowed per client per minute
        """
        super().__init__(app)
        self.enabled = enabled
        self.requests_per_minute = requests_per_minute
        self.logger = logging.getLogger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request with rate limiting (placeholder).
        
        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler
            
        Returns:
            Response from the next handler
        """
        if self.enabled:
            # Placeholder: In production, check rate limits here
            # Could use Redis, in-memory cache with sliding window, etc.
            client_id = request.client.host if request.client else "unknown"
            self.logger.debug(
                "Rate limit check (placeholder)",
                extra={
                    "client_id": client_id,
                    "limit": self.requests_per_minute,
                },
            )
        
        response: Response = await call_next(request)
        return response


__all__ = [
    "RequestIDMiddleware",
    "LoggingContextMiddleware",
    "RateLimitMiddleware",
    "get_request_id",
    "request_id_context",
]
