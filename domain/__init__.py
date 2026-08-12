# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Domain layer containing core bounded contexts.

The package is organised according to domain-driven design (DDD) principles
with dedicated subpackages for orders, positions, and signals.
"""

from .orders import Order, OrderSide, OrderStatus, OrderType
from .portfolio import (
    CorporateActionRecord,
    CurrencyExposureSnapshot,
    FXRates,
    PortfolioAccounting,
    PortfolioSnapshot,
    PositionSnapshot,
)
from .positions import Position
from .signals import Signal, SignalAction

__all__ = [
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PortfolioAccounting",
    "PortfolioSnapshot",
    "Position",
    "PositionSnapshot",
    "Signal",
    "SignalAction",
    "CorporateActionRecord",
    "CurrencyExposureSnapshot",
    "FXRates",
]
