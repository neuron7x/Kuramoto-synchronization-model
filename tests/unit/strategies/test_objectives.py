# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for strategy objective functions."""

import numpy as np
import pytest

from core.strategies.objectives import sharpe_ratio


def test_sharpe_ratio_positive_returns_with_risk_free_offset():
    """Sharpe ratio handles positive returns with a non-zero risk-free rate."""

    returns = np.array([0.05, 0.07, 0.06, 0.08])
    risk_free = 0.02

    result = sharpe_ratio(returns, risk_free=risk_free)

    expected = 3.485685011586675
    assert result == pytest.approx(expected, rel=1e-12)


def test_sharpe_ratio_uniform_returns_zero_variance():
    """Sharpe ratio is zero when returns have no variance."""

    returns = np.array([0.03, 0.03, 0.03, 0.03])

    result = sharpe_ratio(returns)

    assert result == 0.0


def test_sharpe_ratio_mixed_returns_with_risk_free_shift():
    """Sharpe ratio remains stable when returns cross zero with a risk-free shift."""

    returns = np.array([-0.02, 0.01, 0.03, -0.01, 0.02])
    risk_free = 0.005

    result = sharpe_ratio(returns, risk_free=risk_free)

    expected = 0.0482242822170412
    assert result == pytest.approx(expected, rel=1e-12)
