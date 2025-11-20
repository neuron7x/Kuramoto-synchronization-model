"""Unit tests for :class:`OnlineSignalForecaster`."""

from __future__ import annotations

import os
from typing import Callable

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

# Ensure module import does not attempt to build the FastAPI app during tests.
os.environ.setdefault("TRADEPULSE_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "test-audit-secret")

from application.api.service import OnlineSignalForecaster, PredictionResponse
from application.trading import signal_to_dto
from domain.signal import SignalAction

pytestmark = pytest.mark.filterwarnings(
    "ignore:'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated.:DeprecationWarning"
)


class _StubPipeline:
    """Lightweight pipeline stub used to bypass the heavy feature pipeline."""

    def __init__(
        self, transform_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None
    ) -> None:
        self._transform_fn = transform_fn or (lambda frame: frame)

    def transform(
        self, frame: pd.DataFrame
    ) -> pd.DataFrame:  # pragma: no cover - trivial
        return self._transform_fn(frame)


@pytest.fixture
def make_forecaster() -> Callable[[pd.DataFrame], OnlineSignalForecaster]:
    def _factory(features: pd.DataFrame) -> OnlineSignalForecaster:
        pipeline = _StubPipeline(lambda _frame: features.copy())
        return OnlineSignalForecaster(pipeline=pipeline)

    return _factory


class TestLatestFeatureVector:
    def test_empty_frame_raises_bad_request(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        forecaster = make_forecaster(pd.DataFrame())

        with pytest.raises(HTTPException) as excinfo:
            forecaster.latest_feature_vector(pd.DataFrame())

        assert excinfo.value.status_code == 400

    def test_all_nan_row_raises_unprocessable_entity(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        features = pd.DataFrame(
            [
                {
                    "macd": np.nan,
                    "macd_signal": np.nan,
                    "macd_histogram": np.nan,
                    "rsi": np.nan,
                    "return_1": np.nan,
                }
            ]
        )
        forecaster = make_forecaster(features)

        with pytest.raises(HTTPException) as excinfo:
            forecaster.latest_feature_vector(features)

        assert excinfo.value.status_code == 422

    def test_valid_row_returns_clean_series(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        features = pd.DataFrame(
            [
                {
                    "macd": 0.1,
                    "macd_signal": 0.08,
                    "macd_histogram": 0.02,
                    "rsi": 53.0,
                    "return_1": 0.005,
                    "queue_imbalance": 0.2,
                    "volatility_20": 0.01,
                }
            ]
        )
        forecaster = make_forecaster(features)

        latest = forecaster.latest_feature_vector(features)

        assert isinstance(latest, pd.Series)
        assert not latest.isna().any()

    def test_missing_macd_feature_raises_unprocessable_entity(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        features = pd.DataFrame(
            [
                {
                    "macd": 0.1,
                    "macd_histogram": 0.03,
                    "rsi": 52.0,
                    "return_1": 0.004,
                }
            ]
        )
        forecaster = make_forecaster(features)

        with pytest.raises(HTTPException) as excinfo:
            forecaster.latest_feature_vector(features)

        assert excinfo.value.status_code == 422


class TestDeriveSignal:
    @pytest.mark.parametrize(
        "series, expected_action",
        [
            (
                pd.Series(
                    {
                        "macd": 1.2,
                        "macd_signal": 0.6,
                        "macd_histogram": 0.6,
                        "rsi": 68.0,
                        "return_1": 0.03,
                        "queue_imbalance": 0.8,
                        "volatility_20": 0.05,
                    }
                ),
                SignalAction.BUY,
            ),
            (
                pd.Series(
                    {
                        "macd": -1.5,
                        "macd_signal": -0.8,
                        "macd_histogram": -0.7,
                        "rsi": 28.0,
                        "return_1": -0.04,
                        "queue_imbalance": -0.7,
                        "volatility_20": 0.03,
                    }
                ),
                SignalAction.SELL,
            ),
            (
                pd.Series(
                    {
                        "macd": 0.02,
                        "macd_signal": 0.03,
                        "macd_histogram": -0.01,
                        "rsi": 49.0,
                        "return_1": 0.0005,
                        "queue_imbalance": 0.01,
                        "volatility_20": 0.02,
                    }
                ),
                SignalAction.HOLD,
            ),
        ],
    )
    def test_action_and_confidence_bounds(
        self,
        series: pd.Series,
        expected_action: SignalAction,
        make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster],
    ) -> None:
        forecaster = make_forecaster(pd.DataFrame([series]))
        horizon = 900

        signal, score = forecaster.derive_signal("BTC-USD", series, horizon)

        assert signal.action == expected_action
        assert signal.metadata["horizon_seconds"] == horizon
        assert pytest.approx(signal.metadata["score"], rel=1e-6) == score
        assert 0.0 <= signal.confidence <= 1.0

        if expected_action is SignalAction.BUY:
            assert score > 0.12
        elif expected_action is SignalAction.SELL:
            assert score < -0.12
        else:
            assert -0.12 <= score <= 0.12

    def test_bullish_macd_convergence_scores_positive(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        series = pd.Series(
            {
                "macd": -0.2,
                "macd_signal": -0.35,
                "macd_histogram": 0.15,
                "rsi": 52.0,
                "return_1": 0.01,
                "queue_imbalance": 0.1,
                "volatility_20": 0.015,
            }
        )
        forecaster = make_forecaster(pd.DataFrame([series]))

        signal, score = forecaster.derive_signal("SOL-USD", series, 600)

        assert score > 0.12
        assert signal.action is SignalAction.BUY
        assert "component_contributions" in signal.metadata
        assert signal.metadata["component_contributions"]["macd_crossover"] > 0
        assert signal.metadata["component_contributions"]["macd_balance"] >= 0

    def test_bearish_macd_convergence_scores_negative(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        series = pd.Series(
            {
                "macd": 0.18,
                "macd_signal": 0.45,
                "macd_histogram": -0.27,
                "rsi": 44.0,
                "return_1": -0.012,
                "queue_imbalance": -0.2,
                "volatility_20": 0.018,
            }
        )
        forecaster = make_forecaster(pd.DataFrame([series]))

        signal, score = forecaster.derive_signal("ADA-USD", series, 600)

        assert score < -0.12
        assert signal.action is SignalAction.SELL
        assert signal.metadata["component_contributions"]["macd_crossover"] < 0
        assert signal.metadata["component_contributions"]["macd_balance"] <= 0

    def test_macd_balance_penalises_large_divergence(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        series = pd.Series(
            {
                "macd": 1.2,
                "macd_signal": 1.05,
                "macd_histogram": 0.6,
                "rsi": 48.0,
                "return_1": 0.0,
                "queue_imbalance": 0.0,
                "volatility_20": 0.01,
            }
        )
        forecaster = make_forecaster(pd.DataFrame([series]))

        signal, _ = forecaster.derive_signal("BTC-USD", series, 600)

        contributions = signal.metadata["component_contributions"]
        divergence_sum = contributions["macd_trend"] + contributions["macd_histogram"]

        # When divergence materially outweighs convergence the balance term should
        # act as a counterweight (negative contribution) to temper the score.
        assert contributions["macd_balance"] < 0
        assert divergence_sum > 0

    def test_macd_balance_rewards_convergence_alignment(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        series = pd.Series(
            {
                "macd": -0.15,
                "macd_signal": -0.45,
                "macd_histogram": -0.3,
                "rsi": 55.0,
                "return_1": 0.0,
                "queue_imbalance": 0.0,
                "volatility_20": 0.012,
            }
        )
        forecaster = make_forecaster(pd.DataFrame([series]))

        signal, _ = forecaster.derive_signal("ETH-USD", series, 600)

        contributions = signal.metadata["component_contributions"]

        # Strong alignment between MACD convergence and divergence should yield a
        # supportive balance term.
        assert contributions["macd_balance"] > 0

    def test_signal_to_dto_in_prediction_response(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        features = pd.DataFrame(
            [
                {
                    "macd": 0.5,
                    "macd_signal": 0.2,
                    "macd_histogram": 0.3,
                    "rsi": 62.0,
                    "return_1": 0.015,
                    "queue_imbalance": 0.4,
                    "volatility_20": 0.01,
                }
            ]
        )
        series = features.iloc[0]
        horizon = 600
        forecaster = make_forecaster(features)

        signal, score = forecaster.derive_signal("ETH-USD", series, horizon)
        response = PredictionResponse(
            symbol="ETH-USD",
            horizon_seconds=horizon,
            score=score,
            signal=signal_to_dto(signal),
        )

        assert response.horizon_seconds == horizon
        assert response.signal["metadata"]["horizon_seconds"] == horizon
        assert response.signal["metadata"]["score"] == pytest.approx(score, rel=1e-6)

    def test_macd_components_flat_state_is_neutral(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        forecaster = make_forecaster(pd.DataFrame())
        components = (
            forecaster._compute_macd_components(  # pylint: disable=protected-access
                macd=0.0,
                macd_signal_line=0.0,
                macd_histogram=0.0,
            )
        )

        assert components["macd_trend"] == pytest.approx(0.0)
        assert components["macd_crossover"] == pytest.approx(0.0)
        assert components["macd_histogram"] == pytest.approx(0.0)
        assert components["macd_balance"] == pytest.approx(0.0)

    def test_macd_components_alignment_bonus_when_in_sync(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        forecaster = make_forecaster(pd.DataFrame())
        components = (
            forecaster._compute_macd_components(  # pylint: disable=protected-access
                macd=0.9,
                macd_signal_line=0.4,
                macd_histogram=0.5,
            )
        )

        assert components["macd_trend"] > 0
        assert components["macd_crossover"] > 0
        assert components["macd_histogram"] > 0
        assert components["macd_balance"] > -0.15

    def test_derive_signal_clamps_confidence(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        series = pd.Series(
            {
                "macd": 3.5,
                "macd_signal": 0.1,
                "macd_histogram": 2.8,
                "rsi": 90.0,
                "return_1": 0.12,
                "queue_imbalance": 2.0,
                "volatility_20": 0.02,
            }
        )
        forecaster = make_forecaster(pd.DataFrame([series]))

        signal, score = forecaster.derive_signal("BTC-USD", series, 1200)
        assert score > 0
        assert signal.confidence == pytest.approx(1.0)
        assert signal.action is SignalAction.BUY

    def test_derive_signal_hold_when_score_below_threshold(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        series = pd.Series(
            {
                "macd": 0.05,
                "macd_signal": 0.04,
                "macd_histogram": 0.01,
                "rsi": 49.5,
                "return_1": 0.0005,
                "queue_imbalance": 0.0,
                "volatility_20": 0.03,
            }
        )
        forecaster = make_forecaster(pd.DataFrame([series]))

        signal, score = forecaster.derive_signal("ETH-USD", series, 600)
        assert abs(score) < 0.12
        assert signal.action is SignalAction.HOLD
        assert 0.0 <= signal.confidence <= 0.2

    def test_normalised_feature_rows_skips_invalid_records(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        rows = pd.DataFrame(
            [
                {"macd": 0.1, "macd_signal": 0.05, "macd_histogram": 0.02},
                {"macd": float("nan"), "macd_signal": 0.1, "macd_histogram": 0.03},
                {"macd": 0.2, "macd_signal": 0.19},
            ],
            index=pd.date_range("2024-01-01", periods=3, freq="1min", tz="UTC"),
        )

        forecaster = make_forecaster(rows)
        normalised = forecaster.normalised_feature_rows(rows, strict=False)
        assert len(normalised) == 1
        timestamp, vector = normalised[0]
        assert timestamp.tzinfo is not None
        assert set(vector.index) >= {"macd", "macd_signal", "macd_histogram"}

    def test_normalised_feature_rows_strict_mode_raises(
        self, make_forecaster: Callable[[pd.DataFrame], OnlineSignalForecaster]
    ) -> None:
        rows = pd.DataFrame(
            [
                {"macd": 0.2, "macd_signal": 0.15, "macd_histogram": float("nan")},
            ],
            index=pd.date_range("2024-01-01", periods=1, freq="1min", tz="UTC"),
        )

        forecaster = make_forecaster(rows)
        with pytest.raises(HTTPException):
            forecaster.normalised_feature_rows(rows, strict=True)
