# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for exchange-specific symbol and quantity normalization."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Dict, Mapping


@dataclass(slots=True, frozen=True)
class SymbolSpecification:
    """Trading constraints for a specific symbol on an exchange."""

    symbol: str
    min_qty: float = 0.0
    min_notional: float = 0.0
    step_size: float = 0.0
    tick_size: float = 0.0


class NormalizationError(ValueError):
    """Raised when a quantity or price violates exchange constraints."""


class SymbolNormalizer:
    """Normalize symbols and enforce venue-specific constraints."""

    _DECIMAL_PRECISION = 28
    _ABS_ALIGNMENT_TOLERANCE = Decimal("1e-12")
    _REL_ALIGNMENT_TOLERANCE = Decimal("1e-8")

    def __init__(
        self,
        symbol_map: Mapping[str, str] | None = None,
        specifications: Mapping[str, SymbolSpecification] | None = None,
    ) -> None:
        self._symbol_map: Dict[str, str] = {
            self._canonical(k): v for k, v in (symbol_map or {}).items()
        }
        self._specs: Dict[str, SymbolSpecification] = {
            self._canonical(spec.symbol): spec for spec in (specifications or {}).values()
        }

    @staticmethod
    def _canonical(symbol: str) -> str:
        return symbol.replace("-", "").replace("_", "").upper()

    def exchange_symbol(self, symbol: str) -> str:
        canonical = self._canonical(symbol)
        return self._symbol_map.get(canonical, canonical)

    def specification(self, symbol: str) -> SymbolSpecification | None:
        canonical = self._canonical(symbol)
        if canonical in self._specs:
            return self._specs[canonical]
        exchange_symbol = self._symbol_map.get(canonical)
        if exchange_symbol is not None:
            canonical_exchange = self._canonical(exchange_symbol)
            return self._specs.get(canonical_exchange)
        return None

    @staticmethod
    def _decimal(value: float) -> Decimal:
        """Create a high-precision decimal from a binary float."""

        return Decimal(str(value))

    @classmethod
    def _round_decimal(cls, value: float, step: float) -> Decimal:
        if step <= 0:
            return cls._decimal(value)
        step_decimal = cls._decimal(step)
        if step_decimal.is_zero():
            return cls._decimal(value)
        with localcontext() as ctx:
            ctx.prec = cls._DECIMAL_PRECISION
            ctx.rounding = ROUND_HALF_UP
            value_decimal = cls._decimal(value)
            steps = (value_decimal / step_decimal).to_integral_value(rounding=ROUND_HALF_UP)
            return steps * step_decimal

    @classmethod
    def _round(cls, value: float, step: float) -> float:
        if step <= 0:
            return value
        normalized = cls._round_decimal(value, step)
        return float(normalized)

    @classmethod
    def _is_aligned(cls, value: float, step: float) -> bool:
        if step <= 0:
            return True
        step_decimal = cls._decimal(step)
        if step_decimal.is_zero():
            return True
        with localcontext() as ctx:
            ctx.prec = cls._DECIMAL_PRECISION
            ctx.rounding = ROUND_HALF_UP
            value_decimal = cls._decimal(value)
            remainder = (value_decimal % step_decimal).normalize()
        if remainder.is_zero():
            return True
        step_abs = step_decimal.copy_abs()
        remainder_abs = remainder.copy_abs()
        tolerance = max(
            cls._ABS_ALIGNMENT_TOLERANCE,
            step_abs * cls._REL_ALIGNMENT_TOLERANCE,
        )
        tolerance = min(step_abs * Decimal("0.1"), tolerance)
        if remainder_abs < tolerance:
            return True
        if (step_abs - remainder_abs) < tolerance:
            return True
        return False

    def round_quantity(self, symbol: str, quantity: float) -> float:
        spec = self.specification(symbol)
        if spec is None:
            return quantity
        return self._round(quantity, spec.step_size)

    def round_price(self, symbol: str, price: float) -> float:
        spec = self.specification(symbol)
        if spec is None:
            return price
        return self._round(price, spec.tick_size)

    def validate(self, symbol: str, quantity: float, price: float | None = None) -> None:
        spec = self.specification(symbol)
        if spec is None:
            return
        if spec.step_size > 0 and not self._is_aligned(quantity, spec.step_size):
            raise NormalizationError(
                f"Quantity {quantity} not aligned to step size {spec.step_size} for {symbol}"
            )
        if quantity < spec.min_qty:
            raise NormalizationError(
                f"Quantity {quantity} below minimum {spec.min_qty} for {symbol}"
            )
        if price is not None:
            if spec.tick_size > 0 and not self._is_aligned(price, spec.tick_size):
                raise NormalizationError(
                    f"Price {price} not aligned to tick size {spec.tick_size} for {symbol}"
                )
        if price is not None and spec.min_notional:
            notional = quantity * price
            if notional < spec.min_notional:
                raise NormalizationError(
                    f"Notional {notional} below minimum {spec.min_notional} for {symbol}"
                )


__all__ = [
    "SymbolSpecification",
    "NormalizationError",
    "SymbolNormalizer",
]
