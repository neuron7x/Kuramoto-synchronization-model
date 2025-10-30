# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np
import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
    from hypothesis.extra.numpy import arrays
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from backtest.engine import Result, walk_forward


class TestBacktestEngineProperties:
    """Property-based tests for walk_forward backtest engine."""

    @settings(max_examples=100, deadline=None)
    @given(
        prices=arrays(
            dtype=np.float64,
            shape=st.integers(min_value=10, max_value=500),
            elements=st.floats(
                min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False
            ),
        ),
        fee=st.floats(min_value=0.0, max_value=0.01),
    )
    def test_zero_signal_yields_zero_pnl(self, prices: np.ndarray, fee: float) -> None:
        """A signal that is always zero should produce zero PnL and zero trades."""

        def zero_signal(p: np.ndarray) -> np.ndarray:
            return np.zeros_like(p)

        result = walk_forward(prices, zero_signal, fee=fee)
        assert result.pnl == pytest.approx(0.0, abs=1e-9)
        assert result.trades == 0
        assert result.max_dd == pytest.approx(0.0, abs=1e-9)

    @settings(max_examples=100, deadline=None)
    @given(
        prices=arrays(
            dtype=np.float64,
            shape=st.integers(min_value=10, max_value=200),
            elements=st.floats(
                min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False
            ),
        ),
        fee=st.floats(min_value=0.0, max_value=0.005),
    )
    def test_fees_reduce_pnl(self, prices: np.ndarray, fee: float) -> None:
        """Higher fees should result in lower or equal PnL."""

        def constant_long(p: np.ndarray) -> np.ndarray:
            return np.ones_like(p)

        result_no_fee = walk_forward(prices, constant_long, fee=0.0)
        result_with_fee = walk_forward(prices, constant_long, fee=fee)

        # With fees, PnL should be less than or equal to no-fee PnL
        assert result_with_fee.pnl <= result_no_fee.pnl + 1e-9

    @settings(max_examples=50, deadline=None)
    @given(
        prices=arrays(
            dtype=np.float64,
            shape=st.integers(min_value=10, max_value=100),
            elements=st.floats(
                min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False
            ),
        )
    )
    def test_max_drawdown_is_non_positive(self, prices: np.ndarray) -> None:
        """Maximum drawdown should always be non-positive."""

        def random_signal(p: np.ndarray) -> np.ndarray:
            rng = np.random.default_rng(42)
            return rng.uniform(-1, 1, size=len(p))

        result = walk_forward(prices, random_signal, fee=0.001)
        assert result.max_dd <= 0.0

    @settings(max_examples=50, deadline=None)
    @given(
        prices=arrays(
            dtype=np.float64,
            shape=st.integers(min_value=5, max_value=50),
            elements=st.floats(
                min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False
            ),
        )
    )
    def test_buy_and_hold_matches_price_change(self, prices: np.ndarray) -> None:
        """Buy and hold strategy PnL should approximately match price change minus fees."""

        def buy_and_hold(p: np.ndarray) -> np.ndarray:
            signal = np.ones_like(p)
            signal[0] = 0  # Start with no position
            return signal

        fee = 0.0005
        result = walk_forward(prices, buy_and_hold, fee=fee)

        # PnL should be approximately price change minus one entry fee
        expected_pnl = float(prices[-1] - prices[0] - fee)
        assert result.pnl == pytest.approx(expected_pnl, rel=1e-6, abs=1e-9)
        assert result.trades == 1  # One entry trade

    def test_invalid_prices_raises_error(self) -> None:
        """Invalid price arrays should raise ValueError."""
        # Empty array
        with pytest.raises(ValueError, match="at least two observations"):
            walk_forward(np.array([]), lambda p: np.array([]), fee=0.001)

        # Single element
        with pytest.raises(ValueError, match="at least two observations"):
            walk_forward(np.array([100.0]), lambda p: np.array([100.0]), fee=0.001)

        # Wrong dimensions
        with pytest.raises(ValueError, match="1-D array"):
            walk_forward(np.array([[100.0, 101.0]]), lambda p: p, fee=0.001)

    def test_mismatched_signal_length_raises_error(self) -> None:
        """Signal function returning wrong length should raise ValueError."""
        prices = np.array([100.0, 101.0, 102.0])

        def bad_signal(p: np.ndarray) -> np.ndarray:
            return np.zeros(len(p) - 1)  # Wrong length

        with pytest.raises(ValueError, match="same length"):
            walk_forward(prices, bad_signal, fee=0.001)

    @settings(max_examples=50, deadline=None)
    @given(
        prices=arrays(
            dtype=np.float64,
            shape=st.integers(min_value=20, max_value=100),
            elements=st.floats(
                min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False
            ),
        )
    )
    def test_trade_count_is_reasonable(self, prices: np.ndarray) -> None:
        """Trade count should be between 0 and number of price changes."""

        def oscillating_signal(p: np.ndarray) -> np.ndarray:
            # Oscillate between -1 and 1
            return np.array([(-1) ** i for i in range(len(p))], dtype=float)

        result = walk_forward(prices, oscillating_signal, fee=0.0)

        # Trades should be at most n-1 position changes
        assert 0 <= result.trades < len(prices)


class TestBacktestResultProperties:
    """Property-based tests for Result dataclass."""

    @settings(max_examples=50, deadline=None)
    @given(
        pnl=st.floats(min_value=-10_000.0, max_value=10_000.0, allow_nan=False),
        max_dd=st.floats(min_value=-10_000.0, max_value=0.0, allow_nan=False),
        trades=st.integers(min_value=0, max_value=10_000),
    )
    def test_result_creation(self, pnl: float, max_dd: float, trades: int) -> None:
        """Result dataclass should hold provided values."""
        result = Result(pnl=pnl, max_dd=max_dd, trades=trades)
        assert result.pnl == pnl
        assert result.max_dd == max_dd
        assert result.trades == trades
        assert result.performance is None
        assert result.report_path is None
