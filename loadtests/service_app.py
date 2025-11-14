"""FastAPI application configured for deterministic load testing."""

from __future__ import annotations

import os
import base64
from pathlib import Path
from secrets import token_urlsafe

from fastapi import FastAPI
import grpc

from application.api.service import create_app
from application.settings import AdminApiSettings
from loadtests.security import configure_security_overrides


def build_app() -> FastAPI:
    """Create a FastAPI instance with deterministic credentials for load tests."""

    configure_security_overrides()
    state_dir = Path("/tmp/tradepulse-loadtest")
    state_dir.mkdir(parents=True, exist_ok=True)
    audit_secret = os.getenv("LOADTEST_AUDIT_SECRET", token_urlsafe(32))
    two_factor_secret = os.getenv("LOADTEST_TWO_FACTOR_SECRET")
    if two_factor_secret is None:
        two_factor_secret = base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")
    settings = AdminApiSettings(
        audit_secret=audit_secret,
        two_factor_secret=two_factor_secret,
        kill_switch_store_path=state_dir / "kill_switch.sqlite",
        config_vault_path=state_dir / "config_vault.json",
    )
    return create_app(settings=settings)


app = build_app()


@app.get("/health")
def health():
    """Liveness check - returns 200 when process is running."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness check - verifies gRPC service is available."""
    try:
        from loadtests.proto import trading_pb2, trading_pb2_grpc
        
        channel = grpc.insecure_channel("127.0.0.1:50051")
        try:
            stub = trading_pb2_grpc.TradingServiceStub(channel)
            stub.GetPositions(trading_pb2.Empty(), timeout=1.0)
        finally:
            channel.close()
    except Exception as e:
        return {"ready": False, "error": str(e)}, 503
    return {"ready": True}


__all__ = ["app", "build_app"]
