# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Metadata and default-feature edge tests for OnlineSignalForecaster."""

from __future__ import annotations

import os
from typing import Callable

import pandas as pd
import pytest

os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")

from application.api.service import OnlineSignalForecaster
from domain.signal import SignalAction


class _StubPipeline:
    def __init__(
        self,
        transform_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    ) -> None:
        self._transform_fn = transform_fn or (lambda frame: frame)

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        return self._transform_fn(frame)


def _forecaster() -> OnlineSignalForecaster:
    return OnlineSignalForecaster(pipeline=_StubPipeline())


def test_flat_signal_has_zero_confidence_and_complete_macd_metadata() -> None:
    series = pd.Series(
        {
            "macd": 0.0,
            "macd_signal": 0.0,
            "macd_histogram": 0.0,
            "rsi": 50.0,
            "return_1": 0.0,
            "queue_imbalance": 0.0,
            "volatility_20": 0.0,
        }
    )

    signal, score = _forecaster().derive_signal("BTC-USD", series, 300)

    assert score == pytest.approx(0.0)
    assert signal.action is SignalAction.HOLD
    assert signal.confidence == pytest.approx(0.0)
    assert signal.metadata["score"] == pytest.approx(0.0)
    assert set(signal.metadata["macd_component_explanations"]) == {
        "macd_trend",
        "macd_crossover",
        "macd_histogram",
        "macd_balance",
    }
    assert all(
        value == pytest.approx(0.0)
        for value in signal.metadata["component_contributions"].values()
    )


def test_missing_optional_features_default_to_neutral_contributions() -> None:
    series = pd.Series(
        {
            "macd": 0.3,
            "macd_signal": 0.1,
            "macd_histogram": 0.2,
        }
    )
    forecaster = _forecaster()

    signal, score = forecaster.derive_signal("ETH-USD", series, 900)
    macd_components = forecaster._compute_macd_components(  # pylint: disable=protected-access
        macd=0.3,
        macd_signal_line=0.1,
        macd_histogram=0.2,
    )

    assert score == pytest.approx(sum(macd_components.values()))
    contributions = signal.metadata["component_contributions"]
    assert contributions["rsi_bias"] == pytest.approx(0.0)
    assert contributions["return_momentum"] == pytest.approx(0.0)
    assert contributions["order_flow"] == pytest.approx(0.0)
    assert contributions["volatility_risk"] == pytest.approx(0.0)


def test_extreme_bearish_score_yields_high_balance_capped_confidence() -> None:
    # Extreme bearish features drive a strong SELL, but confidence is the
    # documented map confidence = min(1.0, |score| / 0.85). It does NOT saturate
    # to 1.0: the three MACD components saturate at -0.26/-0.22/-0.18 (tanh) and
    # the balance-correction leg has a structural positive floor (~+0.16) that
    # opposes one-sided runaway, so |score| is bounded ~0.78 < 0.85 for any
    # input. Asserting the real contract instead of an unreachable clamp value.
    series = pd.Series(
        {
            "macd": -3.5,
            "macd_signal": -0.1,
            "macd_histogram": -2.8,
            "rsi": 10.0,
            "return_1": -0.12,
            "queue_imbalance": -2.0,
            "volatility_20": 0.02,
        }
    )

    signal, score = _forecaster().derive_signal("SOL-USD", series, 1_200)

    assert score < 0
    assert signal.action is SignalAction.SELL
    assert signal.confidence == pytest.approx(min(1.0, abs(score) / 0.85))
    assert signal.confidence > 0.85  # extreme inputs → high, balance-capped
