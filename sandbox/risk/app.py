"""FastAPI application for the sandbox risk layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from ..clients import ControlClient
from ..models import AuditEvent, KillSwitchState, OrderTicket, TradingSignal
from ..settings import RiskSettings, risk_settings
from .engine import (
    AuditLoggerProtocol,
    KillSwitchProviderProtocol,
    RiskEngine,
    RiskLimits,
)


class ControlKillSwitchProvider(KillSwitchProviderProtocol):
    def __init__(self, client: ControlClient) -> None:
        self._client = client

    async def state(self) -> KillSwitchState:
        return await self._client.kill_switch()


class ControlAuditLogger(AuditLoggerProtocol):
    def __init__(self, client: ControlClient) -> None:
        self._client = client

    async def emit(self, event: AuditEvent) -> None:
        try:
            await self._client.emit_audit_event(event)
        except Exception:  # pragma: no cover - control channel fallback
            # Audit logging failures must not block order evaluation in the sandbox.
            return


def create_engine(settings: RiskSettings) -> RiskEngine:
    control_client = ControlClient(str(settings.control_url))
    limits = RiskLimits(
        max_position=settings.max_position, max_notional=settings.max_notional
    )
    return RiskEngine(
        limits=limits,
        kill_switch=ControlKillSwitchProvider(control_client),
        audit_logger=ControlAuditLogger(control_client),
    )


def create_app(
    settings: RiskSettings | None = None, engine: RiskEngine | None = None
) -> FastAPI:
    config = settings or risk_settings()
    risk_engine = engine or create_engine(config)

    app = FastAPI(title="TradePulse Sandbox Risk Engine", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc),
            "limits": {
                "max_position": config.max_position,
                "max_notional": config.max_notional,
            },
        }

    @app.post("/risk/evaluate")
    async def evaluate(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            order = OrderTicket.model_validate(payload["order"])
            signal = TradingSignal.model_validate(payload["signal"])
        except KeyError as error:
            raise HTTPException(
                status_code=422, detail=f"Missing field: {error.args[0]}"
            ) from error
        decision = await risk_engine.evaluate(order, signal)
        return decision.model_dump()

    return app
