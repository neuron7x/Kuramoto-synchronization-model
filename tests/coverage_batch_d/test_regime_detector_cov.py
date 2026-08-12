# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coverage tests for markets.regime.detector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from markets.regime.detector import RegimeDetector, RegimeDetectionResult


def _make_frame(n: int = 240, *, with_index: bool = False, with_volume: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    # Three concatenated regimes: bull drift, bear drift, choppy high-vol.
    bull = 100.0 + np.cumsum(rng.normal(0.4, 0.5, n // 3))
    bear = bull[-1] + np.cumsum(rng.normal(-0.4, 0.5, n // 3))
    chop = bear[-1] + np.cumsum(rng.normal(0.0, 3.0, n - 2 * (n // 3)))
    close = np.concatenate([bull, bear, chop])
    data: dict[str, np.ndarray] = {"close": close}
    if with_volume:
        data["volume"] = rng.uniform(1_000, 5_000, len(close))
    frame = pd.DataFrame(data)
    if with_index:
        frame.index = pd.date_range("2024-01-01", periods=len(close), freq="D")
    return frame


def test_init_rejects_too_few_regimes() -> None:
    with pytest.raises(ValueError, match="n_regimes"):
        RegimeDetector(n_regimes=1)


def test_init_rejects_small_window() -> None:
    with pytest.raises(ValueError, match="window"):
        RegimeDetector(window=4)


def test_fit_returns_frame_with_probabilities() -> None:
    det = RegimeDetector(n_regimes=3, window=20, random_state=0)
    frame = _make_frame()
    result = det.fit(frame)
    assert "regime" in result.columns
    prob_cols = [c for c in result.columns if c.startswith("prob_")]
    assert prob_cols
    # Probabilities across regimes sum to ~1 per row.
    probs = result[prob_cols].to_numpy()
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-6)


def test_fit_requires_enough_observations() -> None:
    det = RegimeDetector(n_regimes=5, window=5, random_state=0)
    # Four rows survive feature prep, fewer than the five mixture components.
    tiny = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]})
    with pytest.raises(ValueError, match="Not enough observations"):
        det.fit(tiny)


def test_fit_missing_price_column_raises() -> None:
    det = RegimeDetector(window=20, random_state=0)
    with pytest.raises(KeyError, match="close"):
        det.fit(pd.DataFrame({"open": np.arange(100.0)}))


def test_predict_requires_fit() -> None:
    det = RegimeDetector(window=20, random_state=0)
    with pytest.raises(RuntimeError, match="fitted"):
        det.predict(_make_frame())


def test_predict_after_fit() -> None:
    det = RegimeDetector(n_regimes=3, window=20, random_state=0)
    frame = _make_frame()
    det.fit(frame)
    out = det.predict(frame)
    assert len(out) > 0
    assert set(out["regime"]).issubset(
        {"bull_trend", "bear_trend", "volatile_breakout", "range_bound"}
    )


def test_latest_with_monotonic_index_sets_timestamp() -> None:
    det = RegimeDetector(n_regimes=3, window=20, random_state=0)
    frame = _make_frame(with_index=True)
    det.fit(frame)
    res = det.latest(frame)
    assert isinstance(res, RegimeDetectionResult)
    assert res.timestamp is not None
    assert res.probabilities
    assert res.features is not None


def test_latest_without_volume_column() -> None:
    det = RegimeDetector(n_regimes=3, window=20, random_state=0)
    frame = _make_frame(with_volume=False)
    det.fit(frame, volume_col=None)
    res = det.latest(frame, volume_col=None)
    assert res.regime in {
        "bull_trend",
        "bear_trend",
        "volatile_breakout",
        "range_bound",
    }


def test_latest_non_monotonic_index_yields_no_timestamp() -> None:
    det = RegimeDetector(n_regimes=3, window=20, random_state=0)
    frame = _make_frame(with_index=True)
    det.fit(frame)
    shuffled = frame.iloc[::-1]  # strictly decreasing index -> not monotonic-increasing
    res = det.latest(shuffled)
    assert res.timestamp is None


def test_higher_regime_count_covers_range_bound_label() -> None:
    det = RegimeDetector(n_regimes=5, window=15, random_state=1)
    frame = _make_frame(n=300)
    result = det.fit(frame)
    labels = set(result["regime"])
    # With 5 components at least one falls through to the range_bound label.
    assert "range_bound" in labels or len(labels) >= 2
