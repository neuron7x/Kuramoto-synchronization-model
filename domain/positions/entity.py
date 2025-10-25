"""Aggregate tracking exposure and profit-and-loss."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.orders import OrderSide


@dataclass(slots=True)
class Position:
    """Track exposure and PnL for a single symbol."""

    symbol: str
    quantity: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be provided")
        if self.quantity == 0 and self.entry_price != 0:
            raise ValueError("entry_price must be zero when quantity is zero")
        if self.quantity != 0 and self.entry_price <= 0:
            raise ValueError("entry_price must be positive when position is open")
        if self.current_price < 0:
            raise ValueError("current_price cannot be negative")

    def apply_fill(self, side: OrderSide | str, quantity: float, price: float) -> None:
        """Update the position given a fill."""

        if quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if price <= 0:
            raise ValueError("fill price must be positive")

        side = OrderSide(side)
        signed_qty = quantity if side is OrderSide.BUY else -quantity
        previous_qty = self.quantity

        if (
            previous_qty == 0
            or (previous_qty > 0 and signed_qty > 0)
            or (previous_qty < 0 and signed_qty < 0)
        ):
            # Adding to existing exposure or opening a new one
            total_abs = abs(previous_qty) + quantity
            if total_abs == 0:
                self.entry_price = price
            else:
                self.entry_price = (
                    (self.entry_price * abs(previous_qty) + price * quantity)
                    / total_abs
                    if abs(previous_qty) > 0
                    else price
                )
            self.quantity = previous_qty + signed_qty
        else:
            # Reducing or flipping exposure
            closing_qty = min(abs(previous_qty), quantity)
            direction = 1.0 if previous_qty > 0 else -1.0
            self.realized_pnl += closing_qty * (price - self.entry_price) * direction
            net_qty = previous_qty + signed_qty
            self.quantity = net_qty
            if net_qty == 0:
                self.entry_price = 0.0
                self.unrealized_pnl = 0.0
            elif abs(net_qty) < abs(previous_qty):
                # Partial reduction keeps prior entry price
                pass
            else:
                # Position flipped to opposite side; reset cost basis
                residual = quantity - closing_qty
                if residual > 0:
                    self.entry_price = price

        self.mark_to_market(price)

    def mark_to_market(self, price: float) -> None:
        """Refresh market price and unrealized PnL."""

        if price <= 0:
            raise ValueError("price must be positive")
        self.current_price = price
        if self.quantity == 0:
            self.unrealized_pnl = 0.0
            return
        direction = 1.0 if self.quantity > 0 else -1.0
        self.unrealized_pnl = (
            direction * abs(self.quantity) * (price - self.entry_price)
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize into primitives for upper layers."""

        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
        }


__all__ = ["Position"]
