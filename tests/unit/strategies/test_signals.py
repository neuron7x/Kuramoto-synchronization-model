"""Unit tests for core strategy signal utilities."""

import numpy as np
import pytest

from core.strategies.signals import moving_average_signal, threshold_signal


def test_moving_average_signal_default_window_produces_expected_signs():
    prices = np.array([1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0])
    signal = moving_average_signal(prices)

    assert signal.shape == prices.shape
    expected = np.array([-1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0])
    np.testing.assert_array_equal(signal, expected)


def test_moving_average_signal_invalid_window_raises_value_error():
    prices = np.array([1.0, 2.0, 3.0])

    with pytest.raises(ValueError):
        moving_average_signal(prices, window=0)

    with pytest.raises(ValueError):
        moving_average_signal(np.array([1.0, 2.0]), window=3)


def test_threshold_signal_with_variable_thresholds():
    prices = np.array([-0.5, 0.0, 0.5, 1.5])

    default_threshold_signal = threshold_signal(prices)
    np.testing.assert_array_equal(default_threshold_signal, np.array([-1.0, -1.0, 1.0, 1.0]))

    variable_threshold_signal = threshold_signal(prices, threshold=0.75)
    np.testing.assert_array_equal(variable_threshold_signal, np.array([-1.0, -1.0, -1.0, 1.0]))
