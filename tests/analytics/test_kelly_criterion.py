# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from analytics.math_trading.kelly_criterion import (
    KellyCriterion,
    KellyParams,
    MultiAssetKelly,
    MultiAssetKellyParams,
)


def test_single_asset_kelly_closed_form():
    params = KellyParams(win_probability=0.6, win_loss_ratio=1.5)
    result = KellyCriterion().compute(params)

    assert pytest.approx(1 / 3, rel=1e-4) == result.optimal_fraction
    assert result.optimal_fraction <= params.max_fraction
    assert result.growth_rate > 0


def test_psd_covariance_non_negative_variance():
    mu = np.array([0.10, 0.08])
    sigma = np.array([[0.02, 0.01], [0.01, 0.02]])
    params = MultiAssetKellyParams(
        expected_returns=mu,
        covariance_matrix=sigma,
        asset_names=("A", "B"),
        max_position=0.8,
        max_leverage=1.5,
    )

    result = MultiAssetKelly().optimize(params)

    assert result.portfolio_variance >= 0
    assert result.sharpe_ratio >= 0


def test_singular_covariance_uses_pinv_and_leverage_cap(caplog):
    mu = np.array([0.08, 0.08])
    sigma = np.array([[0.04, 0.04], [0.04, 0.04]])
    params = MultiAssetKellyParams(
        expected_returns=mu,
        covariance_matrix=sigma,
        asset_names=("X", "Y"),
        max_position=0.5,
        max_leverage=0.5,
        fractional_kelly=0.8,
    )

    with caplog.at_level("WARNING"):
        result = MultiAssetKelly().optimize(params)

    assert any("ill-conditioned" in message for message in caplog.messages)
    assert result.leverage <= params.max_leverage + 1e-8


def test_kelly_monotonicity_with_win_probability():
    higher_params = KellyParams(win_probability=0.65, win_loss_ratio=1.5)
    lower_params = KellyParams(win_probability=0.55, win_loss_ratio=1.5)

    higher = KellyCriterion().compute(higher_params)
    lower = KellyCriterion().compute(lower_params)

    assert higher.optimal_fraction >= lower.optimal_fraction


@settings(max_examples=25, deadline=None)
@given(
    expected_returns=st.lists(
        st.floats(min_value=-0.05, max_value=0.2, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    ),
    matrix_entries=st.lists(
        st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False),
        min_size=9,
        max_size=9,
    ),
    fractional=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
    max_position=st.floats(min_value=0.2, max_value=2.0, allow_nan=False, allow_infinity=False),
    max_leverage=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
def test_multi_asset_properties(
    expected_returns: list[float],
    matrix_entries: list[float],
    fractional: float,
    max_position: float,
    max_leverage: float,
):
    mu = np.array(expected_returns)
    matrix = np.array(matrix_entries).reshape(3, 3)
    covariance = matrix @ matrix.T + np.eye(3) * 1e-3

    params = MultiAssetKellyParams(
        expected_returns=mu,
        covariance_matrix=covariance,
        asset_names=("A", "B", "C"),
        max_position=max_position,
        max_leverage=max_leverage,
        fractional_kelly=fractional,
    )

    result = MultiAssetKelly().optimize(params)

    assert np.isfinite(result.expected_return)
    assert np.isfinite(result.portfolio_variance)
    assert np.isfinite(result.growth_rate)
    assert result.leverage <= params.max_leverage + 1e-8
    assert result.portfolio_variance >= 0
