"""Market data connectors wrapping ingestion adapters with schema-aware payloads."""

from tradepulse.core.data.dead_letter import DeadLetterItem, DeadLetterQueue

from .market import (
    BaseMarketDataConnector,
    BinanceMarketDataConnector,
    CoinbaseMarketDataConnector,
    PolygonMarketDataConnector,
)

__all__ = [
    "BaseMarketDataConnector",
    "BinanceMarketDataConnector",
    "CoinbaseMarketDataConnector",
    "DeadLetterItem",
    "DeadLetterQueue",
    "PolygonMarketDataConnector",
]
