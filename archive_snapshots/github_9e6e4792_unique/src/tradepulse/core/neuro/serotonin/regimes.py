from __future__ import annotations

import numpy as np

from tradepulse.core.neuro.numeric_config import STABILITY_EPSILON

_EPS = STABILITY_EPSILON


def _to_array(series) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    if arr.ndim != 1:
        raise ValueError("series must be 1-D")
    if len(arr) < 2:
        raise ValueError("series must contain at least 2 points")
    return arr


def _pct_returns(prices: np.ndarray) -> np.ndarray:
    prev = prices[:-1]
    curr = prices[1:]
    denom = np.where(prev == 0.0, _EPS, prev)
    return (curr - prev) / denom


def _reconstruct(start: float, returns: np.ndarray) -> np.ndarray:
    prices = np.empty(len(returns) + 1, dtype=float)
    prices[0] = float(start)
    cumulative = np.cumprod(1.0 + returns, dtype=float)
    prices[1:] = start * cumulative
    return prices


def build_regimes(series, seed: int) -> dict[str, np.ndarray]:
    """Generate deterministic stress regimes from a price series.

    Args:
        series: 1-D array-like of prices.
        seed: RNG seed to ensure deterministic generation.

    Returns:
        Mapping of regime name to price series (numpy arrays).
    """

    prices = _to_array(series)
    base_returns = _pct_returns(prices)
    rng = np.random.default_rng(int(seed))

    regimes: dict[str, np.ndarray] = {}

    # R0: Calm (unchanged)
    regimes["calm"] = prices.copy()

    # R1: High-vol (amplify returns, keep bounded)
    vol_scale = 2.5
    high_vol = np.clip(base_returns * vol_scale, -0.5, 0.5)
    regimes["high_vol"] = _reconstruct(prices[0], high_vol)

    # R2: Flash-crash (sharp drop then recovery)
    crash_returns = base_returns.copy()
    crash_len = max(2, min(5, len(crash_returns) // 10))
    start_idx = int(rng.integers(1, max(2, len(crash_returns) - crash_len)))
    crash_returns[start_idx : start_idx + crash_len] = -0.2
    recover_len = min(len(crash_returns) - (start_idx + crash_len), crash_len)
    if recover_len > 0:
        crash_returns[start_idx + crash_len : start_idx + crash_len + recover_len] = 0.1
    regimes["flash_crash"] = _reconstruct(prices[0], crash_returns)

    # R3: Whipsaw (alternating returns with bounded amplitude)
    whipsaw_returns = np.empty_like(base_returns)
    base_std = float(np.std(base_returns))
    amp = max(0.01, base_std if base_std > 0 else 0.01)
    signs = np.where(np.arange(len(whipsaw_returns)) % 2 == 0, 1.0, -1.0)
    noise = rng.uniform(0.5, 1.2, size=len(whipsaw_returns))
    whipsaw_returns[:] = np.clip(signs * amp * noise, -0.2, 0.2)
    regimes["whipsaw"] = _reconstruct(prices[0], whipsaw_returns)

    # R4: Drift (add deterministic trend)
    drift_strength = 0.0008
    drift_returns = base_returns + drift_strength
    regimes["drift"] = _reconstruct(prices[0], drift_returns)

    # R5: Noise-burst (localized high-frequency noise)
    noise_returns = base_returns.copy()
    burst_len = max(3, min(12, len(noise_returns) // 8))
    burst_start = int(rng.integers(1, max(2, len(noise_returns) - burst_len)))
    burst_noise = rng.normal(0.0, 0.05, size=burst_len)
    noise_returns[burst_start : burst_start + burst_len] += burst_noise
    noise_returns = np.clip(noise_returns, -0.4, 0.4)
    regimes["noise_burst"] = _reconstruct(prices[0], noise_returns)

    return regimes
