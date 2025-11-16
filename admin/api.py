"""Admin API for secure risk control operations.

Provides endpoints for:
- Toggling kill-switch
- Inspecting risk compliance state
- Circuit breaker state

Security features:
- Bearer token authentication
- Rate limiting
- CORS protection
- Security headers
- Localhost-only binding by default
- Comprehensive audit logging
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

__all__ = ["create_admin_app", "KillSwitchRequest", "RiskStateResponse"]


# Configure module logger
logger = logging.getLogger(__name__)

security = HTTPBearer()

# Simple in-memory rate limiting (for production, use Redis)
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


class KillSwitchRequest(BaseModel):
    """Request to toggle the kill switch."""

    enabled: bool


class RiskStateResponse(BaseModel):
    """Response containing current risk state."""

    kill_switch: bool
    max_notional_per_order: float
    max_gross_exposure: float
    daily_max_drawdown_threshold: float
    daily_max_drawdown_mode: str
    daily_high_equity: float
    last_trip_reason: Optional[str]
    last_trip_time: Optional[str]
    open_orders_count: int
    timestamp: str
    circuit_breaker_state: Optional[str] = None
    circuit_breaker_ttl: Optional[float] = None
    circuit_breaker_last_trip: Optional[str] = None


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    """Verify the admin API token.

    Args:
        credentials: HTTP bearer token from request

    Returns:
        True if token is valid

    Raises:
        HTTPException: If token is invalid or missing
    """
    expected_token = os.environ.get("ADMIN_API_TOKEN")
    if not expected_token:
        logger.error("Admin API token not configured in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API token not configured",
        )

    if credentials.credentials != expected_token:
        logger.warning("Failed authentication attempt with invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug("Token verified successfully")
    return True


def rate_limit_check(identifier: str, max_calls: int = 10, window: int = 60) -> bool:
    """Simple rate limiting implementation.
    
    Args:
        identifier: Unique identifier for rate limiting (e.g., IP address)
        max_calls: Maximum number of calls allowed in the window
        window: Time window in seconds
    
    Returns:
        True if rate limit is not exceeded, False otherwise
    """
    now = time.time()
    cutoff = now - window
    
    # Clean old entries
    _rate_limit_store[identifier] = [
        ts for ts in _rate_limit_store[identifier] if ts > cutoff
    ]
    
    # Check rate limit
    if len(_rate_limit_store[identifier]) >= max_calls:
        return False
    
    # Record this request
    _rate_limit_store[identifier].append(now)
    return True


def create_admin_app(
    risk_compliance: Optional[object] = None,
    circuit_breaker: Optional[object] = None,
) -> FastAPI:
    """Create FastAPI application for admin endpoints.

    Args:
        risk_compliance: RiskCompliance instance (optional)
        circuit_breaker: CircuitBreaker instance (optional)

    Returns:
        FastAPI application with security middleware
        
    Security:
        - Rate limiting: 10 requests per minute per IP
        - CORS: Restricted to same origin by default
        - Authentication: Bearer token required for all admin endpoints
        - Security headers: HSTS, CSP, X-Frame-Options, etc.
    """
    app = FastAPI(
        title="TradePulse Admin API",
        description="Secure admin endpoints for risk controls",
        version="1.0.0",
    )
    
    # Add CORS middleware with restrictive defaults
    allowed_origins = os.environ.get(
        "ADMIN_API_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8000"
    ).split(",")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    
    # Add security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """Add security headers to all responses."""
        # Check rate limit
        client_ip = request.client.host if request.client else "unknown"
        rate_limit_max = int(os.environ.get("ADMIN_API_RATE_LIMIT_MAX", "10"))
        rate_limit_window = int(os.environ.get("ADMIN_API_RATE_LIMIT_WINDOW", "60"))
        
        if not rate_limit_check(client_ip, rate_limit_max, rate_limit_window):
            return HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
            )
        
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response

    @app.post("/admin/risk/kill_switch", status_code=status.HTTP_200_OK)
    def toggle_kill_switch(
        request: KillSwitchRequest,
        _authorized: bool = Security(verify_token),
    ) -> dict:
        """Toggle the global kill switch.

        Args:
            request: Kill switch enable/disable request
            _authorized: Token verification result

        Returns:
            Success message with new state
        """
        if risk_compliance is None:
            logger.error("Kill switch toggle attempted but risk_compliance not configured")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Risk compliance not configured",
            )

        action = "enabled" if request.enabled else "disabled"
        logger.info(f"Kill switch toggle requested: {action}")
        
        try:
            risk_compliance.set_kill_switch(request.enabled)
            logger.info(f"Kill switch successfully {action}")
        except Exception as error:
            logger.error(f"Failed to set kill switch: {error}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to toggle kill switch: {str(error)}",
            ) from error

        return {
            "success": True,
            "kill_switch": request.enabled,
            "message": f"Kill switch {action}",
        }

    @app.get("/admin/risk/state", response_model=RiskStateResponse)
    def get_risk_state(
        _authorized: bool = Security(verify_token),
    ) -> RiskStateResponse:
        """Get current risk compliance and circuit breaker state.

        Args:
            _authorized: Token verification result

        Returns:
            Current risk state
        """
        if risk_compliance is None:
            logger.error("Risk state requested but risk_compliance not configured")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Risk compliance not configured",
            )

        logger.debug("Retrieving risk compliance state")
        try:
            state = risk_compliance.get_state()
            response_data = RiskStateResponse(**state)

            if circuit_breaker is not None:
                response_data.circuit_breaker_state = circuit_breaker.state.value
                response_data.circuit_breaker_ttl = circuit_breaker.get_time_until_recovery()
                last_trip = circuit_breaker.get_last_trip_reason()
                response_data.circuit_breaker_last_trip = last_trip
                logger.debug(f"Circuit breaker state: {response_data.circuit_breaker_state}")

            logger.info(f"Risk state retrieved: kill_switch={response_data.kill_switch}")
            return response_data
        except Exception as error:
            logger.error(f"Failed to retrieve risk state: {error}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve risk state: {str(error)}",
            ) from error

    @app.get("/health")
    def health_check() -> dict:
        """Health check endpoint (no auth required).

        Returns:
            Health status
        """
        return {"status": "healthy"}

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_admin_app()
    # Security: Only bind to localhost by default in production
    # Set ADMIN_API_HOST environment variable to override
    host = os.environ.get("ADMIN_API_HOST", "127.0.0.1")
    port = int(os.environ.get("ADMIN_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
