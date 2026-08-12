# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FastAPI application exposing the sandbox mock market."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from ..audit import InMemoryAuditLog
from ..models import PriceSeries
from ..settings import MarketSettings, market_settings
from .generator import MarketDataset


class MarketService:
    def __init__(self, settings: MarketSettings) -> None:
        dataset = MarketDataset(settings.symbols, settings.price_window)
        self._prices = dataset.build()
        self._audit = InMemoryAuditLog()

    def symbols(self) -> list[str]:
        return list(self._prices.keys())

    def prices(self, symbol: str) -> PriceSeries:
        normalized = symbol.lower()
        if normalized not in self._prices:
            raise KeyError(normalized)
        return self._prices[normalized]

    def audit_log(self) -> InMemoryAuditLog:
        return self._audit


def get_service(settings: MarketSettings = Depends(market_settings)) -> MarketService:
    return MarketService(settings)


def create_app(service: MarketService | None = None) -> FastAPI:
    market_service = service or MarketService(market_settings())
    app = FastAPI(title="GeoSync Sandbox Mock Market", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc),
            "symbols": market_service.symbols(),
        }

    @app.get("/symbols")
    async def symbols() -> list[str]:
        return market_service.symbols()

    @app.get("/prices/{symbol}")
    async def prices(symbol: str, window: int | None = None) -> dict[str, Any]:
        try:
            series = market_service.prices(symbol)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found") from error
        points = series.points[-window:] if window else series.points
        event = market_service.audit_log().emit(
            source="mock-market",
            category="prices",
            message=f"price_snapshot::{symbol.lower()}",
            payload={"count": len(points)},
        )
        return {
            "symbol": symbol.lower(),
            "points": [point.model_dump() for point in points],
            "audit_id": event.created_at.isoformat(),
        }

    return app
