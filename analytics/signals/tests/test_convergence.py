"""Unit tests for the convergence detector module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.signals import (
    ConvergenceConfig,
    ConvergenceDetector,
    compute_convergence,
    is_convergent,
)


def _make_linear_series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.RangeIndex(len(values)), dtype=float)


def test_convergence_alignment_detects_consensus() -> None:
    price = _make_linear_series([100, 101, 103, 104, 106])
    macd = _make_linear_series([0.1, 0.2, 0.4, 0.6, 0.9])
    rsi = _make_linear_series([40, 45, 52, 58, 65])

    detector = ConvergenceDetector(ConvergenceConfig(window=1, method="diff"))
    scores = detector.compute({"price": price, "macd": macd, "rsi": rsi})

    latest = scores.latest()
    assert pytest.approx(latest["alignment"], rel=1e-6) == 1.0
    assert pytest.approx(latest["support_ratio"], rel=1e-6) == 1.0
    assert latest["strength_diff"] >= 0.0


def test_convergence_penalises_divergent_signal() -> None:
    price = _make_linear_series([100, 99, 98, 97, 96])  # down trend
    macd = _make_linear_series([1.0, 0.9, 0.7, 0.6, 0.4])  # down trend
    rsi = _make_linear_series([55, 53, 50, 47, 44])  # down trend
    contrary = _make_linear_series([10, 11, 12, 13, 14])  # up trend

    scores = compute_convergence(
        {"price": price, "macd": macd, "rsi": rsi, "volume": contrary},
        config=ConvergenceConfig(window=1, method="diff"),
    )

    alignment = scores.alignment.iloc[-1]
    support_ratio = scores.support_ratio.iloc[-1]
    assert alignment < 0.0  # Majority still points downwards
    assert support_ratio == pytest.approx(0.75)


def test_is_convergent_thresholds_filter_noise() -> None:
    price = _make_linear_series([100, 100.0001, 100.0003, 100.0006])
    macd = _make_linear_series([0.05, 0.051, 0.052, 0.053])
    rsi = _make_linear_series([49.9, 50.1, 50.3, 50.5])

    config = ConvergenceConfig(window=1, method="diff", tolerance=1e-3)
    detector = ConvergenceDetector(config)
    scores = detector.compute({"price": price, "macd": macd, "rsi": rsi})

    flags = is_convergent(
        scores,
        alignment_threshold=0.9,
        support_ratio_threshold=0.8,
        strength_diff_threshold=0.0,
    )

    assert flags.iloc[-1]  # Noise filtered out by tolerance


def test_convergence_accepts_dataframe_input() -> None:
    index = pd.RangeIndex(5)
    data = pd.DataFrame(
        {
            "price": np.linspace(100, 104, num=5),
            "macd": np.linspace(-0.5, 0.5, num=5),
            "rsi": np.linspace(45, 55, num=5),
        },
        index=index,
    )

    detector = ConvergenceDetector(ConvergenceConfig(window=2, method="pct"))
    scores = detector.compute(data)

    assert len(scores.alignment) == len(index)
    assert not scores.support_ratio.isna().all()
