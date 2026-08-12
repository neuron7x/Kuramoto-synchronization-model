# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic scenario generation for stress-testing trading strategies.

This module provides deterministic, parameterised scenario generation that models
volatility regime shifts, liquidity shocks, structural breaks, and order book
morphology changes. The API is intentionally declarative so that tests and
research pipelines can describe complex market conditions while retaining
reproducibility via explicit seeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

NDArrayF64 = NDArray[np.float64]


@dataclass(slots=True)
class VolatilityShift:
    """Temporary multiplier applied to the base volatility."""

    start: int
    duration: int
    multiplier: float
    label: str | None = None

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("start must be non-negative")
        if self.duration <= 0:
            raise ValueError("duration must be strictly positive")
        if self.multiplier <= 0.0:
            raise ValueError("multiplier must be greater than zero")

    def is_active(self, index: int) -> bool:
        return self.start <= index < self.start + self.duration


@dataclass(slots=True)
class LiquidityShock:
    """Liquidity reduction with optional spread widening."""

    start: int
    duration: int
    severity: float
    spread_widening: float = 0.0
    imbalance_shift: float = 0.0
    label: str | None = None

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("start must be non-negative")
        if self.duration <= 0:
            raise ValueError("duration must be strictly positive")
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be between 0 and 1")
        if self.spread_widening < -0.99:
            raise ValueError("spread_widening cannot shrink the spread below 1% of base")

    def is_active(self, index: int) -> bool:
        return self.start <= index < self.start + self.duration


@dataclass(slots=True)
class StructuralBreak:
    """Persistent change in drift and/or volatility."""

    start: int
    new_drift: float | None = None
    new_volatility: float | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("start must be non-negative")
        if self.new_volatility is not None and self.new_volatility <= 0.0:
            raise ValueError("new_volatility must be positive when provided")


@dataclass(slots=True)
class OrderBookDepthProfile:
    """Snapshot of the synthetic order book state."""

    mid_price: float
    bid_prices: NDArrayF64
    ask_prices: NDArrayF64
    bid_sizes: NDArrayF64
    ask_sizes: NDArrayF64
    top_of_book_spread: float

    def total_bid_volume(self) -> float:
        return float(self.bid_sizes.sum())

    def total_ask_volume(self) -> float:
        return float(self.ask_sizes.sum())

    def to_dict(self) -> dict[str, float | list[float]]:
        return {
            "mid_price": float(self.mid_price),
            "bid_prices": self.bid_prices.tolist(),
            "ask_prices": self.ask_prices.tolist(),
            "bid_sizes": self.bid_sizes.tolist(),
            "ask_sizes": self.ask_sizes.tolist(),
            "top_of_book_spread": float(self.top_of_book_spread),
        }


@dataclass(slots=True)
class OrderBookDepthConfig:
    """Configuration for synthesising order book depth profiles."""

    levels: int = 5
    base_spread: float = 0.0005
    tick_size: float = 0.0001
    base_quantity: float = 10_000.0
    depth_shape: Sequence[float] | None = None
    imbalance: float = 0.0
    volatility_spread_sensitivity: float = 0.5

    def __post_init__(self) -> None:
        if self.levels <= 0:
            raise ValueError("levels must be positive")
        if self.base_spread <= 0.0:
            raise ValueError("base_spread must be positive")
        if self.tick_size <= 0.0:
            raise ValueError("tick_size must be positive")
        if self.base_quantity <= 0.0:
            raise ValueError("base_quantity must be positive")
        if abs(self.imbalance) >= 1.0:
            raise ValueError("imbalance must be in the interval (-1, 1)")
        if self.volatility_spread_sensitivity < 0.0:
            raise ValueError("volatility_spread_sensitivity must be non-negative")
        if self.depth_shape is not None and len(self.depth_shape) != self.levels:
            raise ValueError("depth_shape must match the number of levels")

    def normalised_depth_shape(self) -> NDArrayF64:
        if self.depth_shape is None:
            weights = np.linspace(1.0, 0.5, self.levels, dtype=float)
        else:
            weights = np.asarray(self.depth_shape, dtype=float)
        if np.any(weights <= 0.0):
            raise ValueError("depth_shape must contain positive weights")
        weights /= np.sum(weights)
        return weights


@dataclass(slots=True)
class SyntheticScenarioConfig:
    """High-level configuration for scenario simulation."""

    length: int = 252
    initial_price: float = 100.0
    dt: float = 1.0 / 252
    drift: float = 0.0
    volatility: float = 0.2
    liquidity: float = 1.0
    order_book: OrderBookDepthConfig = field(default_factory=OrderBookDepthConfig)
    random_seed: int | None = None
    name_template: str = "Scenario {index}"

    def __post_init__(self) -> None:
        if self.length <= 1:
            raise ValueError("length must be greater than 1 to simulate returns")
        if self.initial_price <= 0.0:
            raise ValueError("initial_price must be positive")
        if self.dt <= 0.0:
            raise ValueError("dt must be positive")
        if self.volatility <= 0.0:
            raise ValueError("volatility must be positive")
        if self.liquidity < 0.0:
            raise ValueError("liquidity must be non-negative")


@dataclass(slots=True)
class SyntheticScenario:
    """Synthetic scenario output capturing prices, liquidity and depth."""

    name: str
    prices: NDArrayF64
    returns: NDArrayF64
    volatility_series: NDArrayF64
    liquidity_series: NDArrayF64
    order_book_profiles: tuple[OrderBookDepthProfile, ...]
    volatility_shifts: tuple[VolatilityShift, ...]
    liquidity_shocks: tuple[LiquidityShock, ...]
    structural_breaks: tuple[StructuralBreak, ...]
    seed: int


@dataclass(slots=True)
class StrategyEvaluation:
    """Result of evaluating a strategy on a synthetic scenario."""

    strategy: str
    scenario: str
    metric: float


@dataclass(slots=True)
class ControlledExperiment:
    """Container bundling scenario and strategy evaluations."""

    scenario: SyntheticScenario
    evaluations: tuple[StrategyEvaluation, ...]


class SyntheticScenarioGenerator:
    """Generate deterministic synthetic market scenarios."""

    def __init__(self, config: SyntheticScenarioConfig) -> None:
        self._config = config

    @property
    def config(self) -> SyntheticScenarioConfig:
        return self._config

    def generate(
        self,
        *,
        n_scenarios: int = 1,
        volatility_shifts: Sequence[VolatilityShift] | None = None,
        liquidity_shocks: Sequence[LiquidityShock] | None = None,
        structural_breaks: Sequence[StructuralBreak] | None = None,
        random_seed: int | None = None,
    ) -> list[SyntheticScenario]:
        """Generate synthetic scenarios configured with deterministic seeds."""

        cfg = self._config
        base_seed = random_seed if random_seed is not None else cfg.random_seed
        seed_sequence = (
            np.random.SeedSequence(base_seed) if base_seed is not None else np.random.SeedSequence()
        )
        scenarios: list[SyntheticScenario] = []
        if n_scenarios <= 0:
            return scenarios
        child_sequences = seed_sequence.spawn(n_scenarios)

        for index, child in enumerate(child_sequences, start=1):
            rng = np.random.default_rng(child)
            seed_value = int(child.entropy)
            scenario = self._generate_single(
                rng=rng,
                scenario_index=index,
                seed_value=seed_value,
                volatility_shifts=tuple(volatility_shifts or ()),
                liquidity_shocks=tuple(liquidity_shocks or ()),
                structural_breaks=tuple(structural_breaks or ()),
            )
            scenarios.append(scenario)
        return scenarios

    def run_controlled_experiments(
        self,
        strategies: Mapping[str, Callable[[SyntheticScenario], float]],
        *,
        scenarios: Sequence[SyntheticScenario],
    ) -> list[ControlledExperiment]:
        """Evaluate strategies on the supplied scenarios.

        The callable for each strategy must accept a :class:`SyntheticScenario` and
        return a numeric metric (e.g., PnL or Sharpe). The function enforces a
        deterministic execution order to keep comparisons reproducible.
        """

        results: list[ControlledExperiment] = []
        for scenario in scenarios:
            evaluations: list[StrategyEvaluation] = []
            for name, strategy in strategies.items():
                metric = float(strategy(scenario))
                evaluations.append(
                    StrategyEvaluation(strategy=name, scenario=scenario.name, metric=metric)
                )
            results.append(
                ControlledExperiment(
                    scenario=scenario,
                    evaluations=tuple(evaluations),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _generate_single(
        self,
        *,
        rng: np.random.Generator,
        scenario_index: int,
        seed_value: int,
        volatility_shifts: tuple[VolatilityShift, ...],
        liquidity_shocks: tuple[LiquidityShock, ...],
        structural_breaks: tuple[StructuralBreak, ...],
    ) -> SyntheticScenario:
        cfg = self._config
        length = cfg.length
        dt = cfg.dt
        sqrt_dt = float(np.sqrt(dt))

        drift_series = np.full(length - 1, cfg.drift, dtype=float)
        volatility_series = np.full(length - 1, cfg.volatility, dtype=float)
        for brk in structural_breaks:
            if brk.start >= length - 1:
                continue
            if brk.new_drift is not None:
                drift_series[brk.start :] = brk.new_drift
            if brk.new_volatility is not None:
                volatility_series[brk.start :] = brk.new_volatility

        volatility_multiplier = np.ones(length - 1, dtype=float)
        for shift in volatility_shifts:
            end_index = min(length - 1, shift.start + shift.duration)
            volatility_multiplier[shift.start : end_index] *= shift.multiplier

        liquidity_scale = np.ones(length - 1, dtype=float)
        spread_multiplier = np.ones(length - 1, dtype=float)
        imbalance_series = np.full(length - 1, cfg.order_book.imbalance, dtype=float)
        for shock in liquidity_shocks:
            end_index = min(length - 1, shock.start + shock.duration)
            liquidity_scale[shock.start : end_index] *= max(1e-6, 1.0 - shock.severity)
            spread_multiplier[shock.start : end_index] *= 1.0 + shock.spread_widening
            imbalance_series[shock.start : end_index] += shock.imbalance_shift

        np.clip(imbalance_series, -0.95, 0.95, out=imbalance_series)

        prices = np.empty(length, dtype=float)
        prices[0] = cfg.initial_price
        log_price = float(np.log(cfg.initial_price))
        returns = np.empty(length - 1, dtype=float)
        effective_vol_series = np.empty(length - 1, dtype=float)
        liquidity_series = cfg.liquidity * liquidity_scale

        base_spread = cfg.order_book.base_spread
        spread_sensitivity = cfg.order_book.volatility_spread_sensitivity
        depth_weights = cfg.order_book.normalised_depth_shape()
        tick_size = cfg.order_book.tick_size
        base_quantity = cfg.order_book.base_quantity

        order_book_profiles: list[OrderBookDepthProfile] = []
        level_steps = np.arange(cfg.order_book.levels, dtype=float)

        for t in range(length - 1):
            mu = drift_series[t]
            sigma = volatility_series[t] * volatility_multiplier[t]
            effective_vol_series[t] = sigma
            drift_term = (mu - 0.5 * sigma**2) * dt
            shock = rng.normal(loc=drift_term, scale=sigma * sqrt_dt)
            log_price += float(shock)
            prices[t + 1] = float(np.exp(log_price))
            returns[t] = prices[t + 1] / prices[t] - 1.0

            volatility_factor = 1.0 + spread_sensitivity * (volatility_multiplier[t] - 1.0)
            spread = base_spread * spread_multiplier[t] * max(volatility_factor, 1e-3)
            imbalance = float(imbalance_series[t])
            bid_multiplier = max(1e-6, 1.0 + imbalance)
            ask_multiplier = max(1e-6, 1.0 - imbalance)
            depth_scale = liquidity_scale[t]
            level_sizes = base_quantity * depth_weights * depth_scale
            bid_sizes = level_sizes * bid_multiplier
            ask_sizes = level_sizes * ask_multiplier
            mid_price = prices[t + 1]
            half_spread = 0.5 * spread
            price_offsets = half_spread + level_steps * tick_size
            bid_prices = mid_price - price_offsets
            ask_prices = mid_price + price_offsets
            profile = OrderBookDepthProfile(
                mid_price=mid_price,
                bid_prices=bid_prices,
                ask_prices=ask_prices,
                bid_sizes=bid_sizes,
                ask_sizes=ask_sizes,
                top_of_book_spread=spread,
            )
            order_book_profiles.append(profile)

        scenario_name = cfg.name_template.format(index=scenario_index)
        return SyntheticScenario(
            name=scenario_name,
            prices=prices,
            returns=returns,
            volatility_series=effective_vol_series,
            liquidity_series=liquidity_series,
            order_book_profiles=tuple(order_book_profiles),
            volatility_shifts=volatility_shifts,
            liquidity_shocks=liquidity_shocks,
            structural_breaks=structural_breaks,
            seed=seed_value,
        )


__all__ = [
    "VolatilityShift",
    "LiquidityShock",
    "StructuralBreak",
    "OrderBookDepthProfile",
    "OrderBookDepthConfig",
    "SyntheticScenarioConfig",
    "SyntheticScenario",
    "StrategyEvaluation",
    "ControlledExperiment",
    "SyntheticScenarioGenerator",
]
