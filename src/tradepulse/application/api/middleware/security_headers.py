# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Security headers middleware for FastAPI."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses.
    
    Implements OWASP security headers recommendations:
    - X-Frame-Options: Prevents clickjacking
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-XSS-Protection: Enables XSS filtering
    - Referrer-Policy: Controls referrer information
    - Content-Security-Policy: Restricts resource loading
    - Strict-Transport-Security: Enforces HTTPS
    - Permissions-Policy: Controls browser features
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        include_csp: bool = True,
        include_hsts: bool = True,
        hsts_max_age: int = 31536000,  # 1 year
        csp_policy: str | None = None,
    ) -> None:
        super().__init__(app)
        self.include_csp = include_csp
        self.include_hsts = include_hsts
        self.hsts_max_age = hsts_max_age
        self.csp_policy = csp_policy or (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to response."""
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS protection (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        if self.include_csp:
            response.headers["Content-Security-Policy"] = self.csp_policy

        # HTTP Strict Transport Security (only for HTTPS)
        if self.include_hsts and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={self.hsts_max_age}; includeSubDomains; preload"
            )

        # Permissions Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        return response
