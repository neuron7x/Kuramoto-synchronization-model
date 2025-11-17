"""Liquidity impact and slippage forecasting utilities.

This module bundles together a light–weight quantitative model that estimates
price impact, expected slippage, entry costs, and execution efficiency metrics
based on order book liquidity.  In addition to analytics, the model can
recommend parameter tweaks for algorithmic execution strategies so they react
automatically to changing market conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Iterable, Sequence

__all__ = [
    "OrderBookLevel",
    "LiquiditySnapshot",
    "LiquidityImpactConfig",
    "ExecutionParameters",
    "ExecutionForecast",
    "LiquidityImpactModel",
]


SideLiteral = str


def _normalise_side(side: SideLiteral) -> SideLiteral:
    side_lower = side.lower()
    if side_lower not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    return side_lower


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """Order book level characterised by price and displayed quantity."""

    price: float
    quantity: float

    def __post_init__(self) -> None:
        if self.price <= 0.0:
            raise ValueError("price must be positive")
        if self.quantity <= 0.0:
            raise ValueError("quantity must be positive")


@dataclass(frozen=True, slots=True)
class LiquiditySnapshot:
    """Immutable snapshot of the top of book liquidity."""

    mid_price: float
    bid_levels: Sequence[OrderBookLevel]
    ask_levels: Sequence[OrderBookLevel]
    timestamp: float | None = None
    volatility: float | None = None

    def __post_init__(self) -> None:
        if self.mid_price <= 0.0:
            raise ValueError("mid_price must be positive")
        object.__setattr__(
            self,
            "bid_levels",
            tuple(sorted(self.bid_levels, key=lambda lvl: lvl.price, reverse=True)),
        )
        object.__setattr__(
            self,
            "ask_levels",
            tuple(sorted(self.ask_levels, key=lambda lvl: lvl.price)),
        )

    def total_depth(self, side: SideLiteral) -> float:
        side_norm = _normalise_side(side)
        levels = self.bid_levels if side_norm == "sell" else self.ask_levels
        return float(sum(level.quantity for level in levels))

    def simulate_market_order(
        self, side: SideLiteral, quantity: float, *, shortfall_penalty_bps: float
    ) -> tuple[float, float, float]:
        """Simulate the book impact of a market order.

        Returns a tuple ``(average_price, filled_from_book, shortfall_quantity)``.
        When the requested ``quantity`` exceeds displayed depth, the residual is
        priced using an extrapolated penalty that approximates walking further
        into the book.
        """

        side_norm = _normalise_side(side)
        if quantity <= 0.0:
            return (self.mid_price, 0.0, 0.0)

        levels = self.ask_levels if side_norm == "buy" else self.bid_levels
        remaining = float(quantity)
        total_value = 0.0
        last_price = self.mid_price
        filled_from_book = 0.0

        for level in levels:
            if remaining <= 0.0:
                break
            take = min(remaining, level.quantity)
            total_value += take * level.price
            remaining -= take
            filled_from_book += take
            last_price = level.price

        shortfall_qty = max(0.0, remaining)
        if shortfall_qty > 0.0:
            penalty = max(shortfall_penalty_bps, 0.0) * 1e-4
            if side_norm == "buy":
                penalty_price = last_price * (1.0 + penalty)
            else:
                penalty_price = max(last_price * (1.0 - penalty), 0.0)
            total_value += shortfall_qty * penalty_price

        average_price = total_value / float(quantity)
        return (average_price, filled_from_book, shortfall_qty)

    def liquidity_score(self, side: SideLiteral, quantity: float) -> float:
        depth = self.total_depth(side)
        if quantity <= 0.0:
            return inf
        return depth / float(quantity)


@dataclass(frozen=True, slots=True)
class LiquidityImpactConfig:
    """Configuration for the liquidity impact model."""

    shortfall_penalty_bps: float = 15.0
    impact_sensitivity: float = 0.05
    participation_exponent: float = 0.6
    volatility_sensitivity: float = 0.04
    slippage_upper_band_bps: float = 15.0
    slippage_lower_band_bps: float = 4.0
    limit_offset_step_bps: float = 2.0
    min_limit_offset_bps: float = 1.0
    max_limit_offset_bps: float = 25.0
    min_participation: float = 0.02
    max_participation: float = 0.5
    max_slice_multiplier: float = 1.5
    min_slice_multiplier: float = 0.6
    liquidity_score_threshold: float = 1.2

    def clamp_participation(self, value: float) -> float:
        return min(max(value, self.min_participation), self.max_participation)

    def clamp_limit_offset(self, value: float) -> float:
        return min(max(value, self.min_limit_offset_bps), self.max_limit_offset_bps)


@dataclass(frozen=True, slots=True)
class ExecutionParameters:
    """Key tunables for an execution schedule."""

    participation_rate: float
    slice_volume: float
    limit_offset_bps: float

    def __post_init__(self) -> None:
        if self.participation_rate <= 0.0:
            raise ValueError("participation_rate must be positive")
        if self.slice_volume <= 0.0:
            raise ValueError("slice_volume must be positive")
        if self.limit_offset_bps < 0.0:
            raise ValueError("limit_offset_bps must be non-negative")


@dataclass(frozen=True, slots=True)
class ExecutionForecast:
    """Output of the liquidity impact model for a single order."""

    side: SideLiteral
    quantity: float
    participation_rate: float
    expected_fill_price: float
    expected_slippage: float
    expected_slippage_bps: float
    expected_cost: float
    liquidity_score: float
    shortfall_ratio: float
    base_market_impact: float
    participation_component: float
    volatility_component: float

    def as_dict(self) -> dict[str, float]:
        return {
            "quantity": self.quantity,
            "expected_fill_price": self.expected_fill_price,
            "expected_slippage": self.expected_slippage,
            "expected_slippage_bps": self.expected_slippage_bps,
            "expected_cost": self.expected_cost,
            "liquidity_score": self.liquidity_score,
            "shortfall_ratio": self.shortfall_ratio,
            "base_market_impact": self.base_market_impact,
            "participation_component": self.participation_component,
            "volatility_component": self.volatility_component,
        }


class LiquidityImpactModel:
    """Model that estimates execution costs and recommends parameter adjustments."""

    def __init__(self, config: LiquidityImpactConfig | None = None) -> None:
        self._config = config or LiquidityImpactConfig()

    @property
    def config(self) -> LiquidityImpactConfig:
        return self._config

    def forecast(
        self,
        *,
        side: SideLiteral,
        quantity: float,
        participation_rate: float,
        snapshot: LiquiditySnapshot,
        volatility: float | None = None,
    ) -> ExecutionForecast:
        side_norm = _normalise_side(side)
        if quantity <= 0.0:
            raise ValueError("quantity must be positive")
        if participation_rate <= 0.0:
            raise ValueError("participation_rate must be positive")

        avg_price, filled_from_book, shortfall_qty = snapshot.simulate_market_order(
            side_norm,
            quantity,
            shortfall_penalty_bps=self._config.shortfall_penalty_bps,
        )

        base_slippage = self._compute_base_slippage(
            side_norm, snapshot.mid_price, avg_price
        )
        effective_participation = min(max(participation_rate, 1e-6), 1.0)
        participation_component = (
            snapshot.mid_price
            * self._config.impact_sensitivity
            * (effective_participation**self._config.participation_exponent)
        )
        realised_volatility = (
            volatility if volatility is not None else snapshot.volatility or 0.0
        )
        volatility_component = (
            snapshot.mid_price
            * self._config.volatility_sensitivity
            * max(realised_volatility, 0.0)
        )

        expected_slippage = (
            base_slippage + participation_component + volatility_component
        )
        expected_slippage_bps = (
            (expected_slippage / snapshot.mid_price) * 1e4
            if snapshot.mid_price
            else 0.0
        )

        if side_norm == "buy":
            expected_fill_price = snapshot.mid_price + expected_slippage
        else:
            expected_fill_price = max(snapshot.mid_price - expected_slippage, 0.0)

        liquidity_score = snapshot.liquidity_score(side_norm, quantity)
        shortfall_ratio = shortfall_qty / quantity
        expected_cost = expected_slippage * quantity

        return ExecutionForecast(
            side=side_norm,
            quantity=quantity,
            participation_rate=participation_rate,
            expected_fill_price=expected_fill_price,
            expected_slippage=expected_slippage,
            expected_slippage_bps=expected_slippage_bps,
            expected_cost=expected_cost,
            liquidity_score=liquidity_score,
            shortfall_ratio=shortfall_ratio,
            base_market_impact=base_slippage,
            participation_component=participation_component,
            volatility_component=volatility_component,
        )

    def _compute_base_slippage(
        self, side: SideLiteral, mid_price: float, avg_price: float
    ) -> float:
        if side == "buy":
            return max(0.0, avg_price - mid_price)
        return max(0.0, mid_price - avg_price)

    def efficiency_metrics(
        self,
        forecast: ExecutionForecast,
        *,
        benchmark_price: float | None = None,
    ) -> dict[str, float]:
        metrics: dict[str, float] = {
            "expected_slippage_bps": forecast.expected_slippage_bps,
            "expected_cost": forecast.expected_cost,
            "liquidity_score": forecast.liquidity_score,
            "shortfall_ratio": forecast.shortfall_ratio,
            "base_market_impact": forecast.base_market_impact,
        }
        if benchmark_price is not None and benchmark_price > 0.0:
            if forecast.side == "buy":
                shortfall = forecast.expected_fill_price - benchmark_price
            else:
                shortfall = benchmark_price - forecast.expected_fill_price
            metrics["expected_implementation_shortfall"] = shortfall
            metrics["expected_implementation_shortfall_bps"] = (
                shortfall / benchmark_price
            ) * 1e4
        return metrics

    def adjust_execution_params(
        self,
        forecast: ExecutionForecast,
        current: ExecutionParameters,
    ) -> ExecutionParameters:
        config = self._config
        slippage_bps = forecast.expected_slippage_bps
        liquidity_score = forecast.liquidity_score

        new_participation = current.participation_rate
        new_slice = current.slice_volume
        new_limit_offset = current.limit_offset_bps

        if slippage_bps > config.slippage_upper_band_bps or liquidity_score < 1.0:
            new_participation = config.clamp_participation(
                current.participation_rate * 0.75
            )
            new_slice = max(
                current.slice_volume * config.min_slice_multiplier,
                current.slice_volume * 0.5,
            )
            new_limit_offset = config.clamp_limit_offset(
                current.limit_offset_bps + config.limit_offset_step_bps
            )
        elif (
            slippage_bps < config.slippage_lower_band_bps
            and liquidity_score > config.liquidity_score_threshold
        ):
            new_participation = config.clamp_participation(
                current.participation_rate * 1.15
            )
            new_slice = min(
                current.slice_volume * config.max_slice_multiplier,
                current.slice_volume * 1.25,
            )
            new_limit_offset = config.clamp_limit_offset(
                max(current.limit_offset_bps - config.limit_offset_step_bps, 0.0)
            )

        # Volatility overrides: if volatility component dominates slippage, be conservative.
        if forecast.volatility_component > forecast.base_market_impact:
            new_participation = config.clamp_participation(new_participation * 0.9)
            new_limit_offset = config.clamp_limit_offset(
                new_limit_offset + config.limit_offset_step_bps / 2
            )

        return ExecutionParameters(
            participation_rate=new_participation,
            slice_volume=new_slice,
            limit_offset_bps=new_limit_offset,
        )

    def batch_forecast(
        self,
        *,
        side: SideLiteral,
        quantities: Iterable[float],
        participation_rate: float,
        snapshot: LiquiditySnapshot,
        volatility: float | None = None,
    ) -> list[ExecutionForecast]:
        return [
            self.forecast(
                side=side,
                quantity=qty,
                participation_rate=participation_rate,
                snapshot=snapshot,
                volatility=volatility,
            )
            for qty in quantities
        ]
