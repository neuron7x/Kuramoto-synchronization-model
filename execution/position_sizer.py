"""Shared utilities for position sizing across execution components."""

from __future__ import annotations

import math

__all__ = ["calculate_position_size"]


def calculate_position_size(
    balance: float,
    risk: float,
    price: float,
    *,
    max_leverage: float = 5.0,
) -> float:
    """Return the position quantity that satisfies the risk budget.

    The helper implements the canonical TradePulse sizing equation used by both
    :class:`execution.order.RiskAwarePositionSizer` and auxiliary utilities.
    ``risk`` is interpreted as a fraction of the available ``balance`` and is
    clipped to the inclusive range ``[0, 1]`` for safety.
    """

    if price <= 0:
        raise ValueError("price must be positive")

    clipped_risk = max(0.0, min(risk, 1.0))
    notional = balance * clipped_risk
    if notional <= 0.0:
        return 0.0

    risk_qty = notional / price
    leverage_cap = (balance * max_leverage) / price
    qty = min(risk_qty, leverage_cap)

    if qty > 0.0 and qty * price > notional:
        qty = math.nextafter(qty, 0.0)
        while qty > 0.0 and qty * price > notional:
            qty = math.nextafter(qty, 0.0)

    return float(max(0.0, qty))
