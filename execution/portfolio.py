# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Portfolio level accounting utilities for realised/unrealised PnL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Mapping

from domain import OrderSide, Position


@dataclass(slots=True)
class PortfolioSnapshot:
    """Immutable view of the portfolio at a point in time."""

    timestamp: datetime
    cash: float
    positions: Mapping[str, Position]
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    net_exposure: float
    equity: float
    fees_paid: float


class PortfolioAccounting:
    """Track cash, positions and PnL with deterministic updates."""

    def __init__(self, *, initial_cash: float = 0.0) -> None:
        self._cash = float(initial_cash)
        self._positions: Dict[str, Position] = {}
        self._realized = 0.0
        self._fees = 0.0

    # ------------------------------------------------------------------
    def apply_fill(
        self,
        symbol: str,
        side: OrderSide | str,
        quantity: float,
        price: float,
        *,
        fees: float = 0.0,
    ) -> None:
        """Update accounting state following an executed fill."""

        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive for fills")

        side = OrderSide(side)
        position = self._positions.setdefault(symbol, Position(symbol=symbol))
        previous_realized = position.realized_pnl
        position.apply_fill(side, quantity, price)
        delta_realized = position.realized_pnl - previous_realized
        self._realized += delta_realized

        notional = quantity * price
        if side is OrderSide.BUY:
            self._cash -= notional
        else:
            self._cash += notional

        if fees:
            if fees < 0:
                raise ValueError("fees cannot be negative")
            self._cash -= fees
            self._fees += fees

    def mark_to_market(self, symbol: str, price: float) -> None:
        """Refresh mark-to-market for ``symbol`` using ``price``."""

        if price <= 0:
            raise ValueError("price must be positive for mark-to-market")
        position = self._positions.get(symbol)
        if position is None:
            return
        position.mark_to_market(price)

    # ------------------------------------------------------------------
    def positions(self) -> Mapping[str, Position]:
        """Return the managed positions."""

        return dict(self._positions)

    def realized_pnl(self) -> float:
        """Return aggregated realised PnL."""

        return self._realized

    def unrealized_pnl(self) -> float:
        """Return aggregated unrealised PnL."""

        return sum(position.unrealized_pnl for position in self._positions.values())

    def gross_exposure(self) -> float:
        """Return total gross exposure in notional terms."""

        return sum(
            abs(position.quantity * position.current_price)
            for position in self._positions.values()
        )

    def net_exposure(self) -> float:
        """Return signed net exposure."""

        return sum(
            position.quantity * position.current_price
            for position in self._positions.values()
        )

    def equity(self) -> float:
        """Return portfolio equity (cash + market value)."""

        market_value = sum(
            position.quantity * position.current_price
            for position in self._positions.values()
        )
        return self._cash + market_value

    def snapshot(self) -> PortfolioSnapshot:
        """Capture current accounting state."""

        timestamp = datetime.now(timezone.utc)
        positions = self.positions()
        unrealized = sum(pos.unrealized_pnl for pos in positions.values())
        gross = sum(abs(pos.quantity * pos.current_price) for pos in positions.values())
        net = sum(pos.quantity * pos.current_price for pos in positions.values())
        equity = self._cash + net
        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=self._cash,
            positions=positions,
            realized_pnl=self._realized,
            unrealized_pnl=unrealized,
            gross_exposure=gross,
            net_exposure=net,
            equity=equity,
            fees_paid=self._fees,
        )


__all__ = ["PortfolioAccounting", "PortfolioSnapshot"]
