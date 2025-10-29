"""Volatility diagnostics and adaptive scaling utilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class VolatilityRegime(str, Enum):
    """Discrete volatility regimes derived from the latest ATR reading."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class VolatilityProfile:
    """Summary of the latest volatility diagnostics used for adaptation."""

    atr: float
    normalized_atr: float
    realized_vol: float
    regime: VolatilityRegime
    regime_score: float
    smoothing_scale: float
    threshold_scale: float
    risk_scale: float


class AtrVolatilityAdapter:
    """Compute volatility regimes and scaling factors based on ATR."""

    def __init__(
        self,
        atr_window: int = 14,
        realized_window: int = 30,
        low_threshold: float = 0.006,
        high_threshold: float = 0.018,
        *,
        low_vol_smoothing: float = 1.3,
        high_vol_smoothing: float = 0.7,
        low_vol_threshold_scale: float = 0.9,
        high_vol_threshold_scale: float = 1.1,
        low_vol_risk_scale: float = 1.3,
        high_vol_risk_scale: float = 0.7,
    ) -> None:
        if atr_window <= 1:
            raise ValueError("atr_window must be greater than one sample")
        if realized_window <= 1:
            raise ValueError("realized_window must be greater than one sample")
        if low_threshold < 0.0 or high_threshold <= 0.0:
            raise ValueError("volatility thresholds must be positive")
        if low_threshold >= high_threshold:
            raise ValueError("low_threshold must be smaller than high_threshold")

        self.atr_window = int(atr_window)
        self.realized_window = int(realized_window)
        self.low_threshold = float(low_threshold)
        self.high_threshold = float(high_threshold)
        self.low_vol_smoothing = float(low_vol_smoothing)
        self.high_vol_smoothing = float(high_vol_smoothing)
        self.low_vol_threshold_scale = float(low_vol_threshold_scale)
        self.high_vol_threshold_scale = float(high_vol_threshold_scale)
        self.low_vol_risk_scale = float(low_vol_risk_scale)
        self.high_vol_risk_scale = float(high_vol_risk_scale)

    def neutral_profile(self) -> VolatilityProfile:
        """Return a neutral (medium regime) profile."""

        midpoint = 0.5
        smoothing = self._interpolate(
            midpoint,
            self.low_vol_smoothing,
            self.high_vol_smoothing,
        )
        threshold_scale = self._interpolate(
            midpoint,
            self.low_vol_threshold_scale,
            self.high_vol_threshold_scale,
        )
        risk_scale = self._interpolate(
            midpoint,
            self.low_vol_risk_scale,
            self.high_vol_risk_scale,
        )
        return VolatilityProfile(
            atr=0.0,
            normalized_atr=0.0,
            realized_vol=0.0,
            regime=VolatilityRegime.MEDIUM,
            regime_score=midpoint,
            smoothing_scale=smoothing,
            threshold_scale=threshold_scale,
            risk_scale=risk_scale,
        )

    def evaluate(
        self,
        df: pd.DataFrame,
        *,
        price_col: str = "close",
        high_col: Optional[str] = "high",
        low_col: Optional[str] = "low",
    ) -> VolatilityProfile:
        """Return a volatility profile for the provided market data."""

        if df.empty or price_col not in df.columns:
            return self.neutral_profile()

        data = df.sort_index()
        close = data[price_col].astype(float)
        high = self._safe_column(data, high_col, fallback=close)
        low = self._safe_column(data, low_col, fallback=close)

        true_range = self._true_range(close, high, low)
        if true_range.size == 0:
            return self.neutral_profile()

        atr = self._atr(true_range)
        realised_vol = self._realised_volatility(close)

        latest_close = float(close.iloc[-1]) if close.size else 0.0
        if not np.isfinite(latest_close) or latest_close == 0.0:
            normalized = 0.0
        else:
            if atr == 0.0 and realised_vol > 0.0:
                atr = realised_vol * abs(latest_close)
            normalized = float(np.clip(atr / abs(latest_close), 0.0, 5.0))

        regime, score = self._classify(normalized)
        smoothing = self._interpolate(
            score,
            self.low_vol_smoothing,
            self.high_vol_smoothing,
        )
        threshold_scale = self._interpolate(
            score,
            self.low_vol_threshold_scale,
            self.high_vol_threshold_scale,
        )
        risk_scale = self._interpolate(
            score,
            self.low_vol_risk_scale,
            self.high_vol_risk_scale,
        )

        return VolatilityProfile(
            atr=float(atr),
            normalized_atr=normalized,
            realized_vol=realised_vol,
            regime=regime,
            regime_score=score,
            smoothing_scale=smoothing,
            threshold_scale=threshold_scale,
            risk_scale=risk_scale,
        )

    def _atr(self, true_range: np.ndarray) -> float:
        if true_range.size < self.atr_window:
            window = true_range.size
        else:
            window = self.atr_window
        if window == 0:
            return 0.0
        series = pd.Series(true_range)
        alpha = 2.0 / (window + 1.0)
        atr_series = series.ewm(alpha=alpha, adjust=False).mean()
        value = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        if not np.isfinite(value):
            return 0.0
        return value

    def _realised_volatility(self, close: pd.Series) -> float:
        if close.size < 2:
            return 0.0
        returns = close.pct_change().dropna()
        if returns.empty:
            return 0.0
        window = min(self.realized_window, returns.size)
        realised = returns.rolling(window).std().iloc[-1]
        if not np.isfinite(realised):
            return 0.0
        return float(realised)

    def _classify(self, normalized_atr: float) -> tuple[VolatilityRegime, float]:
        if normalized_atr <= self.low_threshold:
            return VolatilityRegime.LOW, 0.0
        if normalized_atr >= self.high_threshold:
            return VolatilityRegime.HIGH, 1.0
        span = self.high_threshold - self.low_threshold
        score = (normalized_atr - self.low_threshold) / span
        score = float(np.clip(score, 0.0, 1.0))
        return VolatilityRegime.MEDIUM, score

    def _interpolate(self, score: float, low_value: float, high_value: float) -> float:
        score = float(np.clip(score, 0.0, 1.0))
        return float((1.0 - score) * low_value + score * high_value)

    def _true_range(
        self,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
    ) -> np.ndarray:
        prev_close = close.shift(1)
        range_components = np.vstack(
            [
                (high - low).to_numpy(copy=False),
                (high - prev_close).abs().to_numpy(copy=False),
                (low - prev_close).abs().to_numpy(copy=False),
            ]
        )
        tr = np.nanmax(range_components, axis=0)
        tr = np.nan_to_num(tr, nan=0.0, posinf=0.0, neginf=0.0)
        return tr

    def _safe_column(
        self,
        df: pd.DataFrame,
        column: Optional[str],
        *,
        fallback: pd.Series,
    ) -> pd.Series:
        if column is None or column not in df.columns:
            return fallback
        series = df[column].reindex(fallback.index).astype(float)
        series = series.fillna(fallback)
        return series
