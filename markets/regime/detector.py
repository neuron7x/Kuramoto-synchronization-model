"""Adaptive market regime detection module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture


@dataclass(frozen=True)
class RegimeDetectionResult:
    """Represents the inferred regime for the latest observation."""

    regime: str
    probabilities: Mapping[str, float]
    timestamp: pd.Timestamp | None = None
    features: pd.Series | None = None


class RegimeDetector:
    """Classifies market regimes based on price and volume dynamics.

    The detector learns unsupervised Gaussian mixture components over a set of
    volatility and momentum features. Each component is mapped to a
    human-readable regime label (e.g. ``bull_trend`` or ``range_bound``). The
    resulting posterior probabilities can be used to adjust signal parameters
    dynamically depending on the prevailing market phase.
    """

    def __init__(
        self,
        n_regimes: int = 3,
        window: int = 60,
        random_state: int | None = None,
    ) -> None:
        if n_regimes < 2:
            raise ValueError("n_regimes must be at least 2")
        if window < 5:
            raise ValueError("window must be at least 5 observations")

        self.n_regimes = n_regimes
        self.window = window
        self.model = GaussianMixture(
            n_components=n_regimes,
            covariance_type="full",
            random_state=random_state,
            reg_covar=1e-6,
        )
        self._regime_labels: dict[int, str] = {}
        self._fitted = False

    def fit(
        self,
        data: pd.DataFrame,
        price_col: str = "close",
        volume_col: str | None = "volume",
    ) -> pd.DataFrame:
        """Fit the detector using historical price/volume data.

        Parameters
        ----------
        data:
            Historical observations sorted by time.
        price_col:
            Column containing trade or close prices.
        volume_col:
            Optional column containing traded volume. If ``None`` volume driven
            features are omitted.

        Returns
        -------
        pandas.DataFrame
            Feature matrix augmented with regime probabilities for each
            observation used during fitting.
        """

        features = self._prepare_features(data, price_col, volume_col)
        if len(features) < self.n_regimes:
            raise ValueError("Not enough observations to fit the model")

        self.model.fit(features.values)
        assignments = self.model.predict(features.values)
        self._regime_labels = self._derive_regime_labels(features, assignments)
        self._fitted = True
        probabilities = self.model.predict_proba(features.values)
        return self._build_detection_frame(features, probabilities)

    def predict(
        self,
        data: pd.DataFrame,
        price_col: str = "close",
        volume_col: str | None = "volume",
    ) -> pd.DataFrame:
        """Predict regimes for the provided observations."""

        if not self._fitted:
            raise RuntimeError("Detector must be fitted before calling predict")

        features = self._prepare_features(data, price_col, volume_col)
        probabilities = self.model.predict_proba(features.values)
        return self._build_detection_frame(features, probabilities)

    def latest(
        self,
        data: pd.DataFrame,
        price_col: str = "close",
        volume_col: str | None = "volume",
    ) -> RegimeDetectionResult:
        """Return the latest regime classification for streaming workflows."""

        frame = self.predict(data, price_col=price_col, volume_col=volume_col)
        last_row = frame.iloc[-1]
        timestamp = frame.index[-1] if frame.index.is_monotonic_increasing else None
        probabilities = {
            regime: float(last_row[f"prob_{regime}"])
            for regime in self._ordered_regimes()
            if f"prob_{regime}" in last_row
        }
        return RegimeDetectionResult(
            regime=str(last_row["regime"]),
            probabilities=probabilities,
            timestamp=timestamp,
            features=last_row.filter(
                regex="^(trend|momentum|volatility|volume_z)"
            ).copy(),
        )

    def _prepare_features(
        self,
        data: pd.DataFrame,
        price_col: str,
        volume_col: str | None,
    ) -> pd.DataFrame:
        if price_col not in data:
            raise KeyError(f"Column '{price_col}' not found in provided data")
        series = data[price_col].astype(float).ffill().bfill()
        returns = series.pct_change().fillna(0.0)
        log_returns = np.log(series.clip(lower=1e-12)).diff().fillna(0.0)
        momentum = series.pct_change(self.window).fillna(0.0)

        volatility = log_returns.rolling(self.window, min_periods=self.window // 2).std(
            ddof=0
        )
        volatility = volatility.bfill().fillna(0.0)
        trend = (
            returns.rolling(self.window, min_periods=self.window // 2)
            .mean()
            .fillna(0.0)
        )

        features = pd.DataFrame(
            {
                "trend": trend,
                "momentum": momentum,
                "volatility": volatility,
            },
            index=data.index,
        )

        if volume_col and volume_col in data:
            volume = data[volume_col].astype(float)
            volume_diff = (
                volume
                - volume.rolling(self.window, min_periods=self.window // 2).mean()
            )
            volume_std = volume.rolling(self.window, min_periods=self.window // 2).std(
                ddof=0
            )
            with np.errstate(divide="ignore", invalid="ignore"):
                volume_z = volume_diff / volume_std
            volume_z = volume_z.replace([np.inf, -np.inf], np.nan).fillna(0.0)
            features["volume_z"] = volume_z
        else:
            features["volume_z"] = 0.0

        features = features.replace([np.inf, -np.inf], np.nan).dropna()
        return features

    def _derive_regime_labels(
        self,
        features: pd.DataFrame,
        assignments: Iterable[int],
    ) -> dict[int, str]:
        summary = (
            features.assign(cluster=list(assignments))
            .groupby("cluster")
            .agg(
                {
                    "trend": "mean",
                    "momentum": "mean",
                    "volatility": "mean",
                    "volume_z": "mean",
                }
            )
        )
        labels: dict[int, str] = {}

        if summary.empty:
            return {int(idx): "range_bound" for idx in range(self.n_regimes)}

        remaining = set(summary.index.tolist())

        # Highest volatility -> volatile regime.
        volatile_idx = summary["volatility"].idxmax()
        labels[volatile_idx] = "volatile_breakout"
        remaining.discard(volatile_idx)

        if remaining:
            remaining_list = sorted(remaining)
            bullish_idx = summary.loc[remaining_list, "trend"].idxmax()
            if summary.loc[bullish_idx, "trend"] > 0:
                labels[bullish_idx] = "bull_trend"
                remaining.discard(bullish_idx)

        if remaining:
            remaining_list = sorted(remaining)
            bearish_idx = summary.loc[remaining_list, "trend"].idxmin()
            if summary.loc[bearish_idx, "trend"] < 0:
                labels[bearish_idx] = "bear_trend"
                remaining.discard(bearish_idx)

        for idx in remaining:
            labels[idx] = "range_bound"

        for idx in range(self.n_regimes):
            labels.setdefault(idx, "range_bound")

        # Ensure deterministic ordering for downstream consumers.
        return {
            int(idx): label
            for idx, label in sorted(labels.items(), key=lambda item: item[0])
        }

    def _build_detection_frame(
        self,
        features: pd.DataFrame,
        probabilities: np.ndarray,
    ) -> pd.DataFrame:
        regime_columns = {
            f"prob_{name}": probabilities[:, comp]
            for comp, name in self._regime_labels.items()
        }
        dominant = np.argmax(probabilities, axis=1)
        regimes = [self._regime_labels.get(int(idx), "range_bound") for idx in dominant]
        frame = features.copy()
        for col, values in regime_columns.items():
            frame[col] = values
        frame["regime"] = regimes
        return frame

    def _ordered_regimes(self) -> list[str]:
        return [self._regime_labels[i] for i in sorted(self._regime_labels)]
