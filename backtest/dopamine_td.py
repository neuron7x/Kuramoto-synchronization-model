# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dopamine-based temporal difference learning for backtesting.

This module implements a fast, Numba-accelerated dopamine TD learning algorithm
that can be used as a signal generator for backtesting. The dopamine-based
reinforcement learning approach models reward prediction error (RPE), tonic and
phasic dopamine levels, and produces trading signals based on these neuroscience-
inspired computations.

**Key components**

* :class:`DopamineTDParams`: Configuration for dopamine TD algorithm parameters.
* :func:`run_vectorized_dopamine_td`: Main entry point for running the algorithm
  on market data.
* :func:`dopamine_td_signal`: Generate position signals from price data.
* :func:`run_dopamine_backtest`: High-level wrapper integrating with the existing
  backtest engine.

**Integration with GeoSync**

This module integrates with the existing backtesting infrastructure in
:mod:`backtest.engine` by providing signal generation functions compatible with
the ``walk_forward`` API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from backtest.engine import walk_forward

try:
    from numba import njit

    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

    def njit(*args, **kwargs):
        """Fallback decorator when Numba is not available."""

        def decorator(func):
            return func

        return decorator


@dataclass
class DopamineTDParams:
    """Configuration parameters for the dopamine TD algorithm.

    Attributes:
        discount_gamma: Temporal discount factor for value estimation (0-1).
        learning_rate_v: Learning rate for value function updates.
        decay_rate: Decay rate for tonic dopamine level updates.
        burst_factor: Multiplicative factor for phasic dopamine bursts.
        k: Sigmoid steepness parameter for dopamine-to-signal mapping.
        theta: Threshold parameter for sigmoid (decision boundary).
        c_novelty: Weight for novelty bonus in reward computation.
    """

    discount_gamma: float = 0.99
    learning_rate_v: float = 0.01
    decay_rate: float = 0.1
    burst_factor: float = 2.0
    k: float = 5.0
    theta: float = 0.5
    c_novelty: float = 0.1


@njit(fastmath=True, cache=True)
def _fast_dopamine_loop(
    returns: NDArray[np.float64],
    novelty_scores: NDArray[np.float64],
    gamma: float,
    lr_v: float,
    decay_rate: float,
    burst_factor: float,
    c_novelty: float,
    k: float,
    theta: float,
) -> Tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Numba-accelerated core loop for dopamine TD computation.

    This function implements the temporal difference learning algorithm with
    dopamine-inspired dynamics. It computes reward prediction error (RPE),
    tonic and phasic dopamine levels, and produces a final dopamine signal
    that can be used for decision making.

    Args:
        returns: Array of price returns at each time step.
        novelty_scores: Array of novelty scores (0 if not provided).
        gamma: Temporal discount factor.
        lr_v: Learning rate for value updates.
        decay_rate: Decay rate for tonic dopamine.
        burst_factor: Multiplicative factor for phasic bursts.
        c_novelty: Weight for novelty bonus.
        k: Sigmoid steepness parameter.
        theta: Sigmoid threshold parameter.

    Returns:
        Tuple of (rpe, tonic, phasic, da_level) arrays.
    """
    n = len(returns)

    rpe = np.zeros(n, dtype=np.float64)
    tonic = np.zeros(n, dtype=np.float64)
    phasic = np.zeros(n, dtype=np.float64)
    da_level = np.zeros(n, dtype=np.float64)

    value_estimate = 0.0
    current_tonic = 0.0
    next_value_estimate = 0.0

    for i in range(n):
        reward = returns[i]

        # Compute reward prediction error (TD error)
        # RPE = reward + gamma * V(s') - V(s)
        rpe_val = reward + gamma * next_value_estimate - value_estimate
        rpe[i] = rpe_val

        # Update value estimate for current state
        value_estimate += lr_v * rpe_val

        # The updated value becomes the next state's value for the next iteration
        next_value_estimate = value_estimate

        # Compute appetitive signal (reward + novelty bonus)
        appetitive = max(0.0, reward + c_novelty * novelty_scores[i])

        # Compute phasic dopamine (positive RPE bursts)
        phasic_val = max(0.0, rpe_val) * burst_factor
        if phasic_val > 2.0:
            phasic_val = 2.0
        phasic[i] = phasic_val

        # Update tonic dopamine with exponential moving average
        alpha = decay_rate
        current_tonic += alpha * (appetitive + phasic_val - current_tonic)
        if current_tonic < 0.0:
            current_tonic = 0.0
        elif current_tonic > 1.0:
            current_tonic = 1.0
        tonic[i] = current_tonic

        # Map tonic dopamine to decision signal via sigmoid
        logit = k * (current_tonic - theta)
        if logit > 10.0:
            logit = 10.0
        elif logit < -10.0:
            logit = -10.0

        da_level[i] = 1.0 / (1.0 + np.exp(-logit))

    return rpe, tonic, phasic, da_level


def run_vectorized_dopamine_td(
    df: pd.DataFrame,
    config: DopamineTDParams,
) -> pd.DataFrame:
    """Run the dopamine TD algorithm on market data.

    This function takes a DataFrame with price data, computes returns, and
    applies the dopamine TD algorithm to generate signals. The output includes
    intermediate computations (RPE, tonic, phasic) as well as the final
    dopamine level.

    Args:
        df: DataFrame with at least a 'close' column containing price data.
            May optionally include a 'novelty' column for novelty scores.
        config: Configuration parameters for the algorithm.

    Returns:
        DataFrame indexed by timestamp with columns:
            - close: Original close prices
            - returns: Computed price returns
            - rpe: Reward prediction error
            - tonic: Tonic dopamine level
            - phasic: Phasic dopamine bursts
            - dopamine: Final dopamine signal (0-1)
    """
    close_prices = df["close"].to_numpy(dtype=np.float64)

    # Compute returns with better memory efficiency
    returns = np.zeros(len(close_prices), dtype=np.float64)
    returns[1:] = np.diff(close_prices) / close_prices[:-1]

    # Get novelty scores if available
    if "novelty" in df.columns:
        novelty = df["novelty"].to_numpy(dtype=np.float64)
    else:
        novelty = np.zeros(len(returns), dtype=np.float64)

    # Run the dopamine TD loop
    rpe, tonic, phasic, da = _fast_dopamine_loop(
        returns,
        novelty,
        config.discount_gamma,
        config.learning_rate_v,
        config.decay_rate,
        config.burst_factor,
        config.c_novelty,
        config.k,
        config.theta,
    )

    # Build output DataFrame
    out = pd.DataFrame(
        {
            "close": close_prices,
            "returns": returns,
            "rpe": rpe,
            "tonic": tonic,
            "phasic": phasic,
            "dopamine": da,
        },
        index=df.index,
    )

    return out


def dopamine_td_signal(
    prices: NDArray[np.float64],
    config: DopamineTDParams | None = None,
) -> NDArray[np.float64]:
    """Generate position signals from price data using dopamine TD.

    This function converts a price array into position signals in the range
    [-1, 1] suitable for use with the backtest engine's walk_forward API.

    Args:
        prices: Array of price data.
        config: Configuration parameters. If None, uses default parameters.

    Returns:
        Array of position signals in [-1, 1] range, where:
            - 1.0 indicates full long position
            - -1.0 indicates full short position
            - 0.0 indicates no position
    """
    if config is None:
        config = DopamineTDParams()

    # Create DataFrame from prices
    df = pd.DataFrame({"close": prices})

    # Run dopamine TD algorithm
    results = run_vectorized_dopamine_td(df, config)

    # Convert dopamine level to position signal
    # Dopamine is in [0, 1], convert to [-1, 1]
    da = results["dopamine"].to_numpy()
    signal = (da - 0.5) * 2.0

    # Clip to ensure range
    signal = np.clip(signal, -1.0, 1.0)

    return signal


def run_dopamine_backtest(
    prices: NDArray[np.float64],
    config: DopamineTDParams | None = None,
    fee: float = 0.0005,
    **kwargs,
):
    """Run backtest using dopamine TD signal generation.

    This is a high-level wrapper that integrates the dopamine TD algorithm
    with the existing walk_forward backtest engine.

    Args:
        prices: Array of price data for backtesting.
        config: Dopamine TD configuration. If None, uses defaults.
        fee: Transaction fee (default: 0.05%).
        **kwargs: Additional arguments passed to walk_forward (e.g., latency,
            slippage, constraints).

    Returns:
        Result object from walk_forward containing performance metrics,
        equity curve, and other backtest results.
    """
    if config is None:
        config = DopamineTDParams()

    def _signal_fn(p: NDArray[np.float64]) -> NDArray[np.float64]:
        """Signal function wrapper for walk_forward API."""
        return dopamine_td_signal(p, config)

    return walk_forward(prices, signal_fn=_signal_fn, fee=fee, **kwargs)
