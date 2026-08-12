# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Value objects and enumerations for order-related concepts."""

from __future__ import annotations

from enum import Enum


class OrderSide(str, Enum):
    """Supported trading directions."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    ICEBERG = "iceberg"


class OrderStatus(str, Enum):
    """Lifecycle states for an order."""

    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


__all__ = ["OrderSide", "OrderStatus", "OrderType"]
