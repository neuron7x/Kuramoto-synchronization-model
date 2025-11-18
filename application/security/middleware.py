"""Security middleware for FastAPI application."""
from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    def __init__(self, app: ASGIApp, config: dict | None = None):
        super().__init__(app)
        self.config = config or {}
        self.headers = self.config.get("headers", self._default_headers())

    @staticmethod
    def _default_headers() -> dict[str, str]:
        """Get default security headers."""
        return {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self';",
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
            "Expires": "0",
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Add security headers
        for header_name, header_value in self.headers.items():
            response.headers[header_name] = header_value
        
        # Remove server identification header
        if "Server" in response.headers:
            response.headers["Server"] = "TradePulse"
        
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate incoming requests for security threats."""

    def __init__(self, app: ASGIApp, config: dict | None = None):
        super().__init__(app)
        self.config = config or {}
        self.max_body_size = self.config.get("max_body_size", 10 * 1024 * 1024)  # 10MB

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate request before processing."""
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_size:
            logger.warning(
                "Request body too large",
                extra={
                    "client_ip": request.client.host if request.client else None,
                    "path": request.url.path,
                    "content_length": content_length,
                },
            )
            return Response(
                content="Request body too large",
                status_code=413,
            )
        
        # Validate headers
        if self._has_suspicious_headers(request):
            logger.warning(
                "Suspicious request headers detected",
                extra={
                    "client_ip": request.client.host if request.client else None,
                    "path": request.url.path,
                    "headers": dict(request.headers),
                },
            )
            return Response(
                content="Invalid request",
                status_code=400,
            )
        
        return await call_next(request)

    @staticmethod
    def _has_suspicious_headers(request: Request) -> bool:
        """Check for suspicious headers that might indicate an attack."""
        suspicious_patterns = [
            "<?xml",
            "<!DOCTYPE",
            "<script",
            "javascript:",
            "onerror=",
            "onclick=",
        ]
        
        for header_value in request.headers.values():
            lower_value = header_value.lower()
            if any(pattern in lower_value for pattern in suspicious_patterns):
                return True
        
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware."""

    def __init__(self, app: ASGIApp, config: dict | None = None):
        super().__init__(app)
        self.config = config or {}
        self.requests_per_minute = self.config.get("requests_per_minute", 1000)
        self._request_counts: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting."""
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        
        # Clean old entries
        if client_ip in self._request_counts:
            self._request_counts[client_ip] = [
                t for t in self._request_counts[client_ip]
                if current_time - t < 60
            ]
        else:
            self._request_counts[client_ip] = []
        
        # Check rate limit
        if len(self._request_counts[client_ip]) >= self.requests_per_minute:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "path": request.url.path,
                    "count": len(self._request_counts[client_ip]),
                },
            )
            return Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )
        
        # Record request
        self._request_counts[client_ip].append(current_time)
        
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            self.requests_per_minute - len(self._request_counts[client_ip])
        )
        
        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests for audit purposes."""

    def __init__(self, app: ASGIApp, config: dict | None = None):
        super().__init__(app)
        self.config = config or {}
        self.audit_logger = logging.getLogger("tradepulse.audit")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response for audit."""
        start_time = time.time()
        
        # Log request
        self.audit_logger.info(
            "Request received",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log exception
            self.audit_logger.error(
                "Request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "client_ip": request.client.host if request.client else None,
                },
                exc_info=True,
            )
            raise
        
        # Log response
        duration = time.time() - start_time
        self.audit_logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": int(duration * 1000),
                "client_ip": request.client.host if request.client else None,
            },
        )
        
        return response


def setup_security_middleware(app: ASGIApp, config: dict | None = None) -> ASGIApp:
    """Setup all security middleware for the application."""
    # Add middleware in order (last added = first executed)
    app.add_middleware(AuditLoggingMiddleware, config=config)
    app.add_middleware(RateLimitMiddleware, config=config)
    app.add_middleware(RequestValidationMiddleware, config=config)
    app.add_middleware(SecurityHeadersMiddleware, config=config)
    
    return app
