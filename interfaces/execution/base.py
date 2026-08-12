# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Execution layer interfaces covering sizing and risk control."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping


class PositionSizer(ABC):
    """Contract for translating risk budgets into order quantities."""

    @abstractmethod
    def size(
        self,
        balance: float,
        risk: float,
        price: float,
        *,
        max_leverage: float = 5.0,
    ) -> float:
        """Return a position size expressed in base units."""


class RiskController(ABC):
    """Contract for enforcing trading risk limits."""

    @abstractmethod
    def validate_order(self, symbol: str, side: str, qty: float, price: float) -> None:
        """Validate an order request prior to submission."""

    @abstractmethod
    def register_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        """Register a fill and update risk exposures."""

    @abstractmethod
    def current_position(self, symbol: str) -> float:
        """Return the current net position for the given symbol."""

    @abstractmethod
    def current_notional(self, symbol: str) -> float:
        """Return the current notional exposure for the given symbol."""

    @property
    @abstractmethod
    def kill_switch(self) -> object | None:
        """Return the kill-switch handle if available."""


class PortfolioRiskAnalyzer(ABC):
    """Contract for computing aggregate risk metrics across positions."""

    @abstractmethod
    def heat(self, positions: Iterable[Mapping[str, float]]) -> float:
        """Compute a scalar risk heat metric for a set of positions."""
