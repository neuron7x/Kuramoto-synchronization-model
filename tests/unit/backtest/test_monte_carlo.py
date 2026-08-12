# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math

import numpy as np
import pytest

from backtest.monte_carlo import (
    MonteCarloConfig,
    evaluate_scenarios,
    generate_monte_carlo_scenarios,
)


def test_generate_monte_carlo_scenarios_basic() -> None:
    prices = np.linspace(100.0, 110.0, num=20)
    config = MonteCarloConfig(
        n_scenarios=5,
        volatility_scale=(0.5, 0.5),
        lag_range=(0, 2),
        dropout_probability=0.1,
        random_seed=123,
    )

    scenarios = generate_monte_carlo_scenarios(prices, config=config)
    assert len(scenarios) == 5
    for scenario in scenarios:
        assert scenario.prices.shape == prices.shape
        assert scenario.returns.size == prices.size - 1
        assert 0.0 <= scenario.dropout_ratio <= 1.0
        assert scenario.volatility_scale == pytest.approx(0.5)
        assert 0 <= scenario.lag <= 2


def test_evaluate_scenarios_produces_reports() -> None:
    prices = np.linspace(50.0, 55.0, num=10)
    scenarios = generate_monte_carlo_scenarios(
        prices,
        config=MonteCarloConfig(n_scenarios=3, random_seed=1, lag_range=(0, 0)),
    )
    benchmark = np.zeros(prices.size - 1, dtype=float)

    reports = evaluate_scenarios(scenarios, benchmark_returns=benchmark)
    assert len(reports) == 3
    for report in reports:
        payload = report.as_dict()
        assert "alpha" in payload and "information_ratio" in payload
        assert payload["turnover"] is None
        assert payload["beta"] is None or isinstance(payload["beta"], float)


def test_monte_carlo_regime_shifts_are_reproducible() -> None:
    prices = np.linspace(80.0, 120.0, num=40)
    config = MonteCarloConfig(
        n_scenarios=4,
        volatility_scale=(0.5, 1.5),
        lag_range=(1, 3),
        dropout_probability=0.25,
        random_seed=99,
    )

    first = generate_monte_carlo_scenarios(prices, config=config)
    second = generate_monte_carlo_scenarios(prices, config=config)

    for scenario_a, scenario_b in zip(first, second):
        assert scenario_a.lag == scenario_b.lag
        assert math.isclose(scenario_a.volatility_scale, scenario_b.volatility_scale)
        assert np.allclose(scenario_a.prices, scenario_b.prices)
        assert np.allclose(scenario_a.returns, scenario_b.returns)
        assert math.isclose(scenario_a.dropout_ratio, scenario_b.dropout_ratio)
        assert 0.0 <= scenario_a.dropout_ratio <= 1.0
        assert (
            config.volatility_scale[0] <= scenario_a.volatility_scale <= config.volatility_scale[1]
        )
