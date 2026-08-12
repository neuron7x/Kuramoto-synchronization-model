# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FastAPI application for the sandbox paper execution service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from pydantic import ValidationError

from ..clients import ControlClient, RiskClient, SignalClient
from ..models import AuditEvent, OrderTicket, RiskDecision, TradingSignal
from ..risk.engine import AuditLoggerProtocol
from ..settings import ExecutionSettings, execution_settings
from .engine import (
    ExecutionEngine,
    ExecutionParameters,
    RiskGatewayProtocol,
    SignalGatewayProtocol,
)


class HttpSignalGateway(SignalGatewayProtocol):
    def __init__(self, client: SignalClient) -> None:
        self._client = client

    async def generate(self, symbol: str) -> TradingSignal:
        return await self._client.generate(symbol)


class HttpRiskGateway(RiskGatewayProtocol):
    def __init__(self, client: RiskClient) -> None:
        self._client = client

    async def evaluate(self, order: OrderTicket, signal: TradingSignal) -> RiskDecision:
        return await self._client.evaluate(order, signal)


class ControlAuditLogger(AuditLoggerProtocol):
    def __init__(self, client: ControlClient) -> None:
        self._client = client

    async def emit(self, event: AuditEvent) -> None:
        try:
            await self._client.emit_audit_event(event)
        except Exception:  # pragma: no cover - control channel fallback
            return


def create_engine(settings: ExecutionSettings) -> ExecutionEngine:
    control_client = ControlClient(str(settings.control_url))
    signal_client = SignalClient(str(settings.signal_url))
    risk_client = RiskClient(str(settings.risk_url))
    params = ExecutionParameters(slippage_bps=settings.slippage_bps)
    return ExecutionEngine(
        signals=HttpSignalGateway(signal_client),
        risk=HttpRiskGateway(risk_client),
        audit=ControlAuditLogger(control_client),
        params=params,
    )


def create_app(
    settings: ExecutionSettings | None = None, engine: ExecutionEngine | None = None
) -> FastAPI:
    config = settings or execution_settings()
    execution_engine = engine or create_engine(config)

    app = FastAPI(title="GeoSync Sandbox Paper Execution", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc),
            "slippage_bps": config.slippage_bps,
        }

    @app.post("/orders")
    async def submit(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            order = OrderTicket.model_validate(payload)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors()) from error
        report = await execution_engine.execute(order)
        return report.model_dump()

    return app
