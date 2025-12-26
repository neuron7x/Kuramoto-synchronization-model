"""Admin API for secure risk control operations.

Provides endpoints for:
- Toggling kill-switch
- Inspecting risk compliance state
- Circuit breaker state
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

__all__ = ["create_admin_app", "KillSwitchRequest", "RiskStateResponse"]


security = HTTPBearer()


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


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> bool:
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API token not configured",
        )

    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
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
        FastAPI application
    """
    app = FastAPI(
        title="TradePulse Admin API",
        description="Secure admin endpoints for risk controls",
        version="1.0.0",
    )

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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Risk compliance not configured",
            )

        risk_compliance.set_kill_switch(request.enabled)

        return {
            "success": True,
            "kill_switch": request.enabled,
            "message": f"Kill switch {'enabled' if request.enabled else 'disabled'}",
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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Risk compliance not configured",
            )

        state = risk_compliance.get_state()
        response_data = RiskStateResponse(**state)

        if circuit_breaker is not None:
            response_data.circuit_breaker_state = circuit_breaker.state.value
            response_data.circuit_breaker_ttl = (
                circuit_breaker.get_time_until_recovery()
            )
            last_trip = circuit_breaker.get_last_trip_reason()
            response_data.circuit_breaker_last_trip = last_trip

        return response_data

    @app.get("/health")
    def health_check() -> dict:
        """Health check endpoint (no auth required).

        Returns:
            Health status
        """
        return {"status": "healthy"}

    return app


if __name__ == "__main__":
    raise SystemExit(
        "Deprecated entrypoint. Use: python -m application.runtime.server --config <path>"
    )
