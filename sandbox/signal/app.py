"""FastAPI application exposing the sandbox signal core."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException

from ..clients import MarketClient
from ..models import PricePoint, PriceSeries
from ..settings import SignalSettings, signal_settings
from .engine import SignalEngine


class HttpMarketProvider:
    def __init__(self, client: MarketClient) -> None:
        self._client = client

    async def fetch(self, symbol: str, window: int) -> PriceSeries:
        payload = await self._client.fetch_prices(symbol, window)
        points = [PricePoint.model_validate(point) for point in payload]
        return PriceSeries(symbol=symbol.lower(), points=points)


def create_app(settings: SignalSettings | None = None) -> FastAPI:
    config = settings or signal_settings()
    market_client = MarketClient(str(config.market_url))
    provider = HttpMarketProvider(market_client)
    engine = SignalEngine(
        provider, sensitivity=config.sensitivity, window=config.analysis_window
    )

    app = FastAPI(title="TradePulse Sandbox Signal Core", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "timestamp": datetime.now(timezone.utc)}

    @app.get("/signals/{symbol}")
    async def generate(symbol: str) -> dict[str, Any]:
        try:
            signal = await engine.generate(symbol)
        except HTTPException:
            raise
        except Exception as error:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=502, detail=str(error)) from error
        return signal.model_dump()

    return app
