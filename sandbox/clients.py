"""HTTP clients used across sandbox services."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping

import httpx

from .models import (
    AuditEvent,
    KillSwitchState,
    OrderTicket,
    RiskDecision,
    TradingSignal,
)


class SandboxHttpClient:
    """Shared async HTTP client factory to ensure consistent timeouts."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url
        self._timeout = timeout

    @asynccontextmanager
    async def client(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as session:
            yield session


class MarketClient:
    def __init__(self, base_url: str) -> None:
        self._client_factory = SandboxHttpClient(base_url)

    async def fetch_prices(self, symbol: str, window: int) -> list[dict[str, Any]]:
        async with self._client_factory.client() as client:
            response = await client.get(f"/prices/{symbol}", params={"window": window})
            response.raise_for_status()
            payload = response.json()
            return payload["points"]


class SignalClient:
    def __init__(self, base_url: str) -> None:
        self._client_factory = SandboxHttpClient(base_url)

    async def generate(self, symbol: str) -> TradingSignal:
        async with self._client_factory.client() as client:
            response = await client.get(f"/signals/{symbol}")
            response.raise_for_status()
            return TradingSignal.model_validate(response.json())


class RiskClient:
    def __init__(self, base_url: str) -> None:
        self._client_factory = SandboxHttpClient(base_url)

    async def evaluate(self, order: OrderTicket, signal: TradingSignal) -> RiskDecision:
        async with self._client_factory.client() as client:
            response = await client.post(
                "/risk/evaluate",
                json={"order": order.model_dump(), "signal": signal.model_dump()},
            )
            response.raise_for_status()
            return RiskDecision.model_validate(response.json())


class ControlClient:
    def __init__(self, base_url: str) -> None:
        self._client_factory = SandboxHttpClient(base_url)

    async def kill_switch(self) -> KillSwitchState:
        async with self._client_factory.client() as client:
            response = await client.get("/kill-switch")
            response.raise_for_status()
            return KillSwitchState.model_validate(response.json())

    async def engage(self, reason: str) -> KillSwitchState:
        async with self._client_factory.client() as client:
            response = await client.post("/kill-switch/engage", json={"reason": reason})
            response.raise_for_status()
            return KillSwitchState.model_validate(response.json())

    async def reset(self) -> KillSwitchState:
        async with self._client_factory.client() as client:
            response = await client.post("/kill-switch/reset")
            response.raise_for_status()
            return KillSwitchState.model_validate(response.json())

    async def emit_audit_event(self, event: AuditEvent) -> None:
        async with self._client_factory.client() as client:
            response = await client.post("/audit/events", json=event.model_dump())
            response.raise_for_status()

    async def emit_structured_event(
        self,
        *,
        source: str,
        category: str,
        message: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        event = AuditEvent(
            source=source,
            category=category,
            message=message,
            created_at=datetime.now(timezone.utc),
            payload=dict(payload or {}),
        )
        await self.emit_audit_event(event)

    async def health(self) -> dict[str, Any]:
        async with self._client_factory.client() as client:
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
