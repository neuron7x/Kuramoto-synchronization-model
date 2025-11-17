from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

from backtest.synthetic import (
    LiquidityShock,
    StructuralBreak,
    SyntheticScenarioConfig,
    SyntheticScenarioGenerator,
    VolatilityShift,
)


def test_generator_reproducible() -> None:
    config = SyntheticScenarioConfig(
        length=16,
        initial_price=101.5,
        dt=1.0 / 252,
        drift=0.01,
        volatility=0.3,
        liquidity=2.0,
        random_seed=42,
    )
    generator = SyntheticScenarioGenerator(config)
    shifts = [VolatilityShift(start=3, duration=4, multiplier=1.7)]
    shocks = [LiquidityShock(start=5, duration=3, severity=0.4, spread_widening=0.25)]
    breaks = [StructuralBreak(start=7, new_drift=0.015, new_volatility=0.4)]

    first = generator.generate(
        n_scenarios=2,
        volatility_shifts=shifts,
        liquidity_shocks=shocks,
        structural_breaks=breaks,
    )
    second = generator.generate(
        n_scenarios=2,
        volatility_shifts=shifts,
        liquidity_shocks=shocks,
        structural_breaks=breaks,
    )

    assert len(first) == len(second) == 2
    for scenario_a, scenario_b in zip(first, second):
        np.testing.assert_allclose(scenario_a.prices, scenario_b.prices)
        np.testing.assert_allclose(scenario_a.returns, scenario_b.returns)
        np.testing.assert_allclose(
            scenario_a.volatility_series, scenario_b.volatility_series
        )
        np.testing.assert_allclose(
            scenario_a.liquidity_series, scenario_b.liquidity_series
        )
        assert scenario_a.seed == scenario_b.seed


def test_volatility_shift_applies_multiplier() -> None:
    config = SyntheticScenarioConfig(
        length=10,
        drift=0.0,
        volatility=0.25,
        dt=1.0 / 252,
        random_seed=7,
    )
    generator = SyntheticScenarioGenerator(config)
    shift = VolatilityShift(start=2, duration=3, multiplier=1.5)

    scenario = generator.generate(volatility_shifts=[shift])[0]
    expected = np.array([0.25] * (config.length - 1))
    expected[2:5] *= 1.5
    np.testing.assert_allclose(scenario.volatility_series, expected)


def test_liquidity_shock_reduces_depth_and_widens_spread() -> None:
    config = SyntheticScenarioConfig(
        length=8,
        drift=0.0,
        volatility=0.2,
        dt=1.0,
        liquidity=1.0,
        random_seed=11,
    )
    generator = SyntheticScenarioGenerator(config)
    shock = LiquidityShock(
        start=2,
        duration=3,
        severity=0.5,
        spread_widening=0.5,
        imbalance_shift=0.2,
    )

    scenario = generator.generate(liquidity_shocks=[shock])[0]
    liquidity_series = scenario.liquidity_series
    assert liquidity_series[2] == pytest.approx(
        config.liquidity * (1.0 - shock.severity)
    )
    assert liquidity_series[1] == pytest.approx(config.liquidity)

    pre_profile = scenario.order_book_profiles[1]
    shock_profile = scenario.order_book_profiles[2]
    assert shock_profile.top_of_book_spread > pre_profile.top_of_book_spread
    assert shock_profile.total_bid_volume() < pre_profile.total_bid_volume()
    assert shock_profile.total_ask_volume() < pre_profile.total_ask_volume()


def test_structural_break_changes_drift_and_volatility() -> None:
    config = SyntheticScenarioConfig(
        length=7,
        drift=0.0,
        volatility=1e-6,
        dt=1.0,
        random_seed=3,
    )
    generator = SyntheticScenarioGenerator(config)
    break_event = StructuralBreak(start=3, new_drift=0.05, new_volatility=0.1)

    scenario = generator.generate(structural_breaks=[break_event])[0]
    np.testing.assert_allclose(
        scenario.volatility_series[:3], np.full(3, config.volatility)
    )
    np.testing.assert_allclose(
        scenario.volatility_series[3:], np.full(config.length - 4, 0.1)
    )
    post_returns = scenario.returns[3:]
    pre_returns = scenario.returns[:3]
    assert np.all(post_returns > 0.0)
    assert float(np.mean(post_returns)) > float(np.mean(pre_returns)) + 0.02
    assert float(np.mean(post_returns)) > 0.03


def test_controlled_experiments_evaluate_strategies() -> None:
    config = SyntheticScenarioConfig(
        length=6, drift=0.0, volatility=0.2, random_seed=21
    )
    generator = SyntheticScenarioGenerator(config)
    scenario = generator.generate()[0]

    strategies = OrderedDict(
        {
            "terminal_return": lambda scn: scn.prices[-1] / scn.prices[0] - 1.0,
            "volatility": lambda scn: float(np.std(scn.returns, ddof=1)),
        }
    )

    experiments = generator.run_controlled_experiments(
        strategies=strategies, scenarios=[scenario]
    )
    assert len(experiments) == 1
    experiment = experiments[0]
    assert experiment.scenario is scenario
    metrics = {
        evaluation.strategy: evaluation.metric for evaluation in experiment.evaluations
    }
    expected_terminal = scenario.prices[-1] / scenario.prices[0] - 1.0
    expected_vol = float(np.std(scenario.returns, ddof=1))
    assert metrics["terminal_return"] == pytest.approx(expected_terminal)
    assert metrics["volatility"] == pytest.approx(expected_vol)
