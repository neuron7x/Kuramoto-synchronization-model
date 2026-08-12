# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Market data connectors wrapping ingestion adapters with schema-aware payloads."""

from core.data.dead_letter import DeadLetterItem, DeadLetterQueue

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
