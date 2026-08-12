"""Normalized order-book imbalance for L2 frames."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _float_field(row: Mapping[str, Any], name: str) -> float:
    value = float(row[name])
    if value != value:
        raise ValueError(f"NaN in {name}")
    return value


def nobi(row: Mapping[str, Any], depth: int) -> float:
    bid_depth = sum(_float_field(row, f"bid_sz_{idx}") for idx in range(1, depth + 1))
    ask_depth = sum(_float_field(row, f"ask_sz_{idx}") for idx in range(1, depth + 1))
    denom = bid_depth + ask_depth
    if denom <= 0.0:
        raise ValueError("NOBI denominator must be positive")
    value = (bid_depth - ask_depth) / denom
    if value != value:
        raise ValueError("NOBI produced NaN")
    return float(value)
