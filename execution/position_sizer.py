"""Shared utilities for position sizing across execution components.

This module provides the core position sizing calculation used throughout
TradePulse for determining trade quantities based on risk budgets and
leverage constraints. The implementation ensures:

1. Risk-based capital allocation (fractional kelly)
2. Leverage limit enforcement
3. Floating-point precision safety
4. Input validation for security

Performance considerations:
- Optimized for hot path usage in backtesting and live trading
- Minimal branching for common case (valid inputs)
- Early exit for zero positions
"""

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

    Args:
        balance: Available capital in account currency (must be non-negative).
        risk: Fraction of capital to deploy (will be clipped to [0, 1]).
        price: Execution price of the instrument (must be positive).
        max_leverage: Maximum allowable leverage multiplier (default 5.0).

    Returns:
        float: Position quantity in base units.

    Raises:
        ValueError: If balance is negative or price is non-positive.
    """
    # Fast path validation - single condition check
    if balance < 0 or price <= 0:
        if balance < 0:
            raise ValueError("balance must be non-negative")
        raise ValueError("price must be positive")

    # Clip risk to valid range [0, 1]
    clipped_risk = max(0.0, min(risk, 1.0))
    notional = balance * clipped_risk

    # Early exit for zero notional
    if notional <= 0.0:
        return 0.0

    # Calculate position size with leverage cap
    risk_qty = notional / price
    leverage_cap = (balance * max_leverage) / price
    qty = min(risk_qty, leverage_cap)

    # Ensure quantity doesn't exceed notional due to floating-point precision
    if qty > 0.0 and qty * price > notional:
        qty = math.nextafter(qty, 0.0)
        while qty > 0.0 and qty * price > notional:
            qty = math.nextafter(qty, 0.0)

    return float(max(0.0, qty))
