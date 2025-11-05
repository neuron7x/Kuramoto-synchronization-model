"""Execution quality analytics utilities."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from statistics import mean
from typing import Iterable, Mapping, Sequence

__all__ = [
    "FillSample",
    "CancelReplaceSample",
    "vwap",
    "implementation_shortfall",
    "vwap_slippage",
    "fill_rate",
    "cancel_replace_latency",
]


@dataclass(frozen=True, slots=True)
class FillSample:
    """Minimal representation of an execution fill."""

    quantity: float
    price: float
    fees: float = 0.0


@dataclass(frozen=True, slots=True)
class CancelReplaceSample:
    """Timestamps for a cancel request and subsequent replace acknowledgement."""

    cancel_ts: float
    replace_ts: float

    def latency(self) -> float:
        return max(0.0, float(self.replace_ts) - float(self.cancel_ts))


def _coerce_fill(
    fill: Mapping[str, float] | FillSample | Mapping[str, object],
) -> FillSample:
    """Coerce a mapping or FillSample into a FillSample instance."""

    if isinstance(fill, FillSample):
        return fill

    if isinstance(fill, Mapping):
        qty_key = "quantity" if "quantity" in fill else "qty"
        price_key = "price"
        fees_key = "fees" if "fees" in fill else None
        quantity = float(fill[qty_key])
        price = float(fill[price_key])
        fees = float(fill.get(fees_key, 0.0)) if fees_key else 0.0
        return FillSample(quantity=quantity, price=price, fees=fees)

    quantity = float(getattr(fill, "quantity"))
    price = float(getattr(fill, "price"))
    fees = float(getattr(fill, "fees", 0.0))
    return FillSample(quantity=quantity, price=price, fees=fees)


def vwap(fills: Sequence[Mapping[str, float] | FillSample] | Sequence[object]) -> float:
    """Compute the volume-weighted average price for a collection of fills."""

    total_qty = 0.0
    total_value = 0.0
    for raw_fill in fills:
        fill = _coerce_fill(raw_fill)
        if fill.quantity <= 0:
            continue
        total_qty += fill.quantity
        total_value += fill.quantity * fill.price
    if total_qty == 0:
        return 0.0
    return total_value / total_qty


def implementation_shortfall(
    side: str,
    arrival_price: float,
    fills: Sequence[Mapping[str, float] | FillSample] | Sequence[object],
    *,
    explicit_fees: float = 0.0,
) -> float:
    """Implementation shortfall relative to an arrival price.

    Positive values indicate performance worse than the benchmark for both buy and
    sell orders. Fees can be provided explicitly or captured per fill.
    """

    side_factor = 1.0 if side.lower() == "buy" else -1.0
    executed_qty = 0.0
    total_cost = 0.0
    total_fees = float(explicit_fees)
    for raw_fill in fills:
        fill = _coerce_fill(raw_fill)
        if fill.quantity <= 0:
            continue
        executed_qty += fill.quantity
        total_cost += fill.quantity * fill.price
        total_fees += fill.fees
    if executed_qty == 0:
        return 0.0
    realized = side_factor * total_cost + total_fees
    benchmark = side_factor * arrival_price * executed_qty
    return realized - benchmark


def vwap_slippage(
    side: str,
    benchmark_price: float,
    fills: Sequence[Mapping[str, float] | FillSample] | Sequence[object],
) -> float:
    """VWAP slippage versus a benchmark price.

    Positive numbers represent slippage against the trader (higher paid for buys,
    lower received for sells).
    """

    trade_vwap = vwap(fills)
    if trade_vwap == 0.0:
        return 0.0
    side_factor = 1.0 if side.lower() == "buy" else -1.0
    return side_factor * (trade_vwap - benchmark_price)


def fill_rate(
    target_quantity: float,
    fills: Sequence[Mapping[str, float] | FillSample] | Sequence[object],
) -> float:
    """Compute the executed quantity as a fraction of the target quantity."""

    if target_quantity <= 0:
        return 0.0
    executed_qty = 0.0
    for raw_fill in fills:
        fill = _coerce_fill(raw_fill)
        if fill.quantity <= 0:
            continue
        executed_qty += fill.quantity
    return max(0.0, min(1.0, executed_qty / float(target_quantity)))


def cancel_replace_latency(
    samples: Iterable[CancelReplaceSample | Mapping[str, float]],
) -> dict[str, float]:
    """Aggregate latency statistics from cancel/replace samples."""

    latencies: list[float] = []
    for sample in samples:
        if isinstance(sample, CancelReplaceSample):
            latency = sample.latency()
        else:
            cancel = float(sample.get("cancel_ts") or sample.get("cancel"))
            replace = float(sample.get("replace_ts") or sample.get("replace"))
            latency = max(0.0, replace - cancel)
        latencies.append(latency)
    if not latencies:
        return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(latencies)
    count = len(ordered)

    def percentile(p: float) -> float:
        if count == 1:
            return ordered[0]
        rank = p * (count - 1)
        low = floor(rank)
        high = ceil(rank)
        if low == high:
            return ordered[low]
        weight = rank - low
        return ordered[low] + (ordered[high] - ordered[low]) * weight

    return {
        "count": float(count),
        "mean": mean(ordered),
        "p50": percentile(0.5),
        "p95": percentile(0.95),
        "max": ordered[-1],
    }
