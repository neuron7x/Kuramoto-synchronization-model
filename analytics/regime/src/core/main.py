"""Market regime detection core module.

This module exposes the :class:`RegimeDetector` class which analyses recent
market data to infer the prevailing market regime across multiple axes
(trend, volatility, liquidity and cross-asset correlation).  The detector
combines robust statistical measures with interpretable heuristics so that it
can be used in both backtests and live trading workflows without introducing
heavy model dependencies.

The implementation intentionally favours numerical stability and
maintainability over raw complexity.  Each helper method focuses on a single
aspect of the regime and returns both the qualitative label and the metrics
used to derive it.  This makes it straightforward to audit decisions and to
feed the diagnostics into observability pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Iterable, Mapping, MutableMapping, Optional

import numpy as np
import pandas as pd


class TrendRegime(Enum):
    """Qualitative description of the directional market regime."""

    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    RANGING = "ranging"


class VolatilityRegime(Enum):
    """Qualitative description of the volatility environment."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class LiquidityRegime(Enum):
    """Qualitative description of the liquidity environment."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class CorrelationRegime(Enum):
    """Qualitative description of the cross-asset correlation structure."""

    DECOUPLED = "decoupled"
    MIXED = "mixed"
    COUPLED = "coupled"


@dataclass(frozen=True)
class DetectorConfig:
    """Configuration for :class:`RegimeDetector`.

    The default values are calibrated to work with hourly or minute level
    price data.  They can be overridden to better fit higher frequency or
    end-of-day use cases.
    """

    trend_window: int = 48
    volatility_window: int = 64
    liquidity_window: int = 64
    correlation_window: int = 64
    trending_zscore: float = 1.0
    mean_reverting_autocorr_threshold: float = -0.05
    liquidity_score_high: float = 0.75
    liquidity_score_low: float = -0.75
    correlation_high_threshold: float = 0.6
    correlation_low_threshold: float = 0.25


@dataclass
class StrategyAdjustments:
    """Suggested strategy adjustments for the detected regime."""

    risk_multiplier: float
    position_scale: float
    execution_style: str
    parameter_overrides: Dict[str, float]
    notes: str


@dataclass
class MarketRegimeSnapshot:
    """Snapshot containing regime labels and diagnostics."""

    trend: TrendRegime
    volatility: VolatilityRegime
    liquidity: LiquidityRegime
    correlation: CorrelationRegime
    adjustments: StrategyAdjustments
    diagnostics: Dict[str, float]


class RegimeDetector:
    """Detect high-level market regimes from recent market data.

    Parameters
    ----------
    config:
        Optional configuration overriding the default windows and thresholds.
    """

    def __init__(self, config: Optional[DetectorConfig] = None) -> None:
        self.config = config or DetectorConfig()

    def detect(
        self,
        prices: Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series,
        *,
        volumes: Optional[
            Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series
        ] = None,
        spreads: Optional[
            Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series
        ] = None,
    ) -> MarketRegimeSnapshot:
        """Detect the current market regime.

        Parameters
        ----------
        prices:
            Price history for one or more instruments.  The data must be
            index-aligned and ordered from oldest to newest.  When a mapping is
            provided it will be converted to a :class:`pandas.DataFrame`.
        volumes:
            Optional traded volumes aligned with ``prices``.
        spreads:
            Optional bid-ask spreads aligned with ``prices``.

        Returns
        -------
        MarketRegimeSnapshot
            The detected regime labels, suggested strategy adjustments and the
            diagnostics used to derive them.
        """

        price_frame = _to_frame(prices, name="price")
        returns = price_frame.pct_change().dropna(how="all")
        if returns.empty:
            raise ValueError("Not enough data to compute returns for regime detection.")

        trend_regime, trend_metrics = self._detect_trend(price_frame, returns)
        volatility_regime, volatility_metrics = self._detect_volatility(returns)
        liquidity_regime, liquidity_metrics = self._detect_liquidity(
            volumes=volumes,
            spreads=spreads,
            fallback_returns=returns,
        )
        correlation_regime, correlation_metrics = self._detect_correlation(returns)

        diagnostics: Dict[str, float] = {}
        diagnostics.update(trend_metrics)
        diagnostics.update(volatility_metrics)
        diagnostics.update(liquidity_metrics)
        diagnostics.update(correlation_metrics)

        adjustments = self._build_adjustments(
            trend_regime=trend_regime,
            volatility_regime=volatility_regime,
            liquidity_regime=liquidity_regime,
            correlation_regime=correlation_regime,
            trend_score=trend_metrics.get("trend_score", 0.0),
            volatility_score=volatility_metrics.get("volatility_score", 0.0),
            liquidity_score=liquidity_metrics.get("liquidity_score", 0.0),
        )

        return MarketRegimeSnapshot(
            trend=trend_regime,
            volatility=volatility_regime,
            liquidity=liquidity_regime,
            correlation=correlation_regime,
            adjustments=adjustments,
            diagnostics=diagnostics,
        )

    def calibrate(
        self,
        prices: Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series,
        *,
        volumes: Optional[
            Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series
        ] = None,
        spreads: Optional[
            Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series
        ] = None,
        trending_quantile: float = 0.85,
        mean_reverting_quantile: float = 0.2,
        liquidity_high_quantile: float = 0.7,
        liquidity_low_quantile: float = 0.3,
        correlation_high_quantile: float = 0.75,
        correlation_low_quantile: float = 0.25,
    ) -> DetectorConfig:
        """Calibrate regime thresholds using historical data.

        The detector analyses rolling windows of the supplied price, volume and
        spread history to derive quantile-based thresholds.  The resulting
        :class:`DetectorConfig` is assigned to ``self.config`` and also
        returned so that it can be persisted by the caller.
        """

        price_frame = _to_frame(prices, name="price")
        returns = price_frame.pct_change().dropna(how="all")
        if returns.empty:
            raise ValueError("Not enough data to compute returns for calibration.")

        volume_frame = _to_optional_frame(volumes, name="volume")
        spread_frame = _to_optional_frame(spreads, name="spread")

        max_window = max(
            self.config.trend_window,
            self.config.liquidity_window,
            self.config.correlation_window,
            4,
        )

        trend_scores: list[float] = []
        autocorrs: list[float] = []
        liquidity_scores: list[float] = []
        correlation_values: list[float] = []

        for end in range(max_window, len(price_frame) + 1):
            window_prices = price_frame.iloc[:end]
            window_returns = window_prices.pct_change().dropna(how="all")
            if window_returns.empty:
                continue

            _, trend_metrics = self._detect_trend(window_prices, window_returns)
            trend_scores.append(trend_metrics["trend_score"])
            autocorrs.append(trend_metrics["trend_autocorr"])

            sub_volumes = volume_frame.iloc[:end] if volume_frame is not None else None
            sub_spreads = spread_frame.iloc[:end] if spread_frame is not None else None
            _, liquidity_metrics = self._detect_liquidity(
                volumes=sub_volumes,
                spreads=sub_spreads,
                fallback_returns=window_returns,
            )
            liquidity_scores.append(liquidity_metrics["liquidity_score"])

            if window_returns.shape[1] >= 2:
                _, correlation_metrics = self._detect_correlation(window_returns)
                correlation_value = correlation_metrics.get("correlation_mean_abs")
                if correlation_value is not None and np.isfinite(correlation_value):
                    correlation_values.append(float(correlation_value))

        if not trend_scores or not liquidity_scores:
            raise ValueError("Not enough data to calibrate regime thresholds.")

        abs_trend_quantile = _finite_quantile(np.abs(trend_scores), trending_quantile)
        if abs_trend_quantile is None:
            trending_zscore = self.config.trending_zscore
        else:
            trending_zscore = max(float(abs_trend_quantile), 1e-3)

        mean_reverting_threshold = _finite_quantile(autocorrs, mean_reverting_quantile)
        if mean_reverting_threshold is None or mean_reverting_threshold >= 0.0:
            mean_reverting_autocorr = self.config.mean_reverting_autocorr_threshold
        else:
            mean_reverting_autocorr = float(mean_reverting_threshold)

        liquidity_high = _finite_quantile(liquidity_scores, liquidity_high_quantile)
        liquidity_low = _finite_quantile(liquidity_scores, liquidity_low_quantile)
        if (
            liquidity_high is None
            or liquidity_low is None
            or liquidity_high <= liquidity_low
        ):
            liquidity_high = self.config.liquidity_score_high
            liquidity_low = self.config.liquidity_score_low

        if correlation_values:
            correlation_high = _finite_quantile(
                correlation_values, correlation_high_quantile
            )
            correlation_low = _finite_quantile(
                correlation_values, correlation_low_quantile
            )
            if correlation_high is not None:
                correlation_high = float(np.clip(correlation_high, 0.0, 1.0))
            if correlation_low is not None:
                correlation_low = float(np.clip(correlation_low, 0.0, 1.0))
            if (
                correlation_high is None
                or correlation_low is None
                or correlation_high < correlation_low
            ):
                correlation_high = self.config.correlation_high_threshold
                correlation_low = self.config.correlation_low_threshold
        else:
            correlation_high = self.config.correlation_high_threshold
            correlation_low = self.config.correlation_low_threshold

        calibrated_config = replace(
            self.config,
            trending_zscore=float(trending_zscore),
            mean_reverting_autocorr_threshold=float(mean_reverting_autocorr),
            liquidity_score_high=float(liquidity_high),
            liquidity_score_low=float(liquidity_low),
            correlation_high_threshold=float(correlation_high),
            correlation_low_threshold=float(correlation_low),
        )

        self.config = calibrated_config
        return calibrated_config

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------
    def _detect_trend(
        self, prices: pd.DataFrame, returns: pd.DataFrame
    ) -> tuple[TrendRegime, Dict[str, float]]:
        window = min(self.config.trend_window, len(prices))
        if window < 4:
            window = len(prices)
        window_prices = prices.tail(window)
        window_returns = returns.tail(max(window - 1, 1))

        cumulative_return = (
            window_prices.iloc[-1] / window_prices.iloc[0] - 1.0
        ).astype(float)
        mean_cum_return = float(cumulative_return.mean())
        volatility = float(window_returns.std(ddof=0).replace(0.0, np.nan).mean())
        volatility = max(volatility, 1e-8)
        trend_score = mean_cum_return / volatility

        # Autocorrelation at lag 1 averaged across instruments.
        autocorrs = []
        for column in window_returns:
            series = window_returns[column].dropna()
            if len(series) > 3:
                autocorrs.append(float(series.autocorr(lag=1)))
        mean_autocorr = float(np.mean(autocorrs)) if autocorrs else 0.0

        if abs(trend_score) >= self.config.trending_zscore:
            regime = TrendRegime.TRENDING
        elif mean_autocorr <= self.config.mean_reverting_autocorr_threshold:
            regime = TrendRegime.MEAN_REVERTING
        else:
            regime = TrendRegime.RANGING

        metrics = {
            "trend_score": trend_score,
            "trend_cumulative_return": mean_cum_return,
            "trend_volatility": volatility,
            "trend_autocorr": mean_autocorr,
        }
        return regime, metrics

    def _detect_volatility(
        self, returns: pd.DataFrame
    ) -> tuple[VolatilityRegime, Dict[str, float]]:
        window = min(self.config.volatility_window, len(returns))
        if window < 2:
            window = len(returns)
        rolling_vol = returns.rolling(window).std(ddof=0).dropna(how="all")
        if rolling_vol.empty:
            rolling_vol = returns.std(ddof=0).to_frame().T

        vol_series = rolling_vol.mean(axis=1)
        current_volatility = float(vol_series.iloc[-1])
        low_threshold = float(vol_series.quantile(0.3))
        high_threshold = float(vol_series.quantile(0.7))

        if current_volatility <= low_threshold:
            regime = VolatilityRegime.LOW
        elif current_volatility >= high_threshold:
            regime = VolatilityRegime.HIGH
        else:
            regime = VolatilityRegime.NORMAL

        # Scale the score using a robust z-score.
        median = float(vol_series.median())
        mad = float((vol_series - median).abs().median()) or 1e-8
        volatility_score = (current_volatility - median) / mad

        metrics = {
            "volatility_current": current_volatility,
            "volatility_low_threshold": low_threshold,
            "volatility_high_threshold": high_threshold,
            "volatility_score": volatility_score,
        }
        return regime, metrics

    def _detect_liquidity(
        self,
        *,
        volumes: Optional[Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series],
        spreads: Optional[Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series],
        fallback_returns: pd.DataFrame,
    ) -> tuple[LiquidityRegime, Dict[str, float]]:
        volume_frame = _to_optional_frame(volumes, name="volume")
        spread_frame = _to_optional_frame(spreads, name="spread")
        window = min(self.config.liquidity_window, len(fallback_returns))
        if window < 2:
            window = len(fallback_returns)

        scores: list[float] = []

        if volume_frame is not None:
            volume_window = volume_frame.tail(window)
            volume_series = volume_frame.rolling(window).mean().dropna(how="all")
            if volume_series.empty:
                volume_series = volume_window.mean(axis=1)
            else:
                volume_series = volume_series.mean(axis=1)
            current_volume = float(volume_window.mean(axis=1).iloc[-1])
            scores.append(_robust_zscore(current_volume, volume_series))

        if spread_frame is not None:
            spread_window = spread_frame.tail(window)
            spread_series = spread_frame.rolling(window).mean().dropna(how="all")
            if spread_series.empty:
                spread_series = spread_window.mean(axis=1)
            else:
                spread_series = spread_series.mean(axis=1)
            current_spread = float(spread_window.mean(axis=1).iloc[-1])
            scores.append(-_robust_zscore(current_spread, spread_series))

        if not scores:
            # Use inverse volatility as a loose proxy when liquidity inputs are
            # not provided. Higher volatility generally implies lower
            # liquidity, hence the negative sign.
            volatility_proxy = fallback_returns.tail(window).std(ddof=0).mean()
            volatility_series = (
                fallback_returns.rolling(window).std(ddof=0).dropna(how="all")
            )
            if volatility_series.empty:
                volatility_series = fallback_returns.std(ddof=0).to_frame().T
            volatility_series = volatility_series.mean(axis=1)
            scores.append(-_robust_zscore(float(volatility_proxy), volatility_series))

        liquidity_score = float(np.mean(scores))
        if liquidity_score >= self.config.liquidity_score_high:
            regime = LiquidityRegime.HIGH
        elif liquidity_score <= self.config.liquidity_score_low:
            regime = LiquidityRegime.LOW
        else:
            regime = LiquidityRegime.MODERATE

        metrics = {
            "liquidity_score": liquidity_score,
        }
        return regime, metrics

    def _detect_correlation(
        self, returns: pd.DataFrame
    ) -> tuple[CorrelationRegime, Dict[str, float]]:
        if returns.shape[1] < 2:
            # With a single asset we cannot infer cross-sectional correlation.
            return CorrelationRegime.MIXED, {"correlation_mean_abs": 0.0}

        window = min(self.config.correlation_window, len(returns))
        if window < 2:
            window = len(returns)
        corr_matrix = returns.tail(window).corr()
        abs_corr = corr_matrix.abs()
        # Exclude the diagonal to avoid biasing the mean towards one.
        upper_triangle = abs_corr.where(
            np.triu(np.ones(abs_corr.shape), k=1).astype(bool)
        )
        upper_values = upper_triangle.stack()
        if upper_values.empty:
            # No pairwise correlations could be computed. Treat this as a
            # neutral reading rather than assuming the market is decoupled.
            mean_abs_corr = float("nan")
            metrics = {
                "correlation_mean_abs": mean_abs_corr,
            }
            return CorrelationRegime.MIXED, metrics

        mean_abs_corr = float(upper_values.mean())

        if mean_abs_corr >= self.config.correlation_high_threshold:
            regime = CorrelationRegime.COUPLED
        elif mean_abs_corr <= self.config.correlation_low_threshold:
            regime = CorrelationRegime.DECOUPLED
        else:
            regime = CorrelationRegime.MIXED

        metrics = {
            "correlation_mean_abs": mean_abs_corr,
        }
        return regime, metrics

    def _build_adjustments(
        self,
        *,
        trend_regime: TrendRegime,
        volatility_regime: VolatilityRegime,
        liquidity_regime: LiquidityRegime,
        correlation_regime: CorrelationRegime,
        trend_score: float,
        volatility_score: float,
        liquidity_score: float,
    ) -> StrategyAdjustments:
        position_scale = 1.0
        risk_multiplier = 1.0
        execution_style = "normal"
        notes: list[str] = []
        parameter_overrides: MutableMapping[str, float] = {}

        if trend_regime is TrendRegime.TRENDING:
            # Encourage trend-following signals while keeping tail-risk in check.
            position_scale *= 1.15
            parameter_overrides["trend_signal_sensitivity"] = min(
                2.0, 1.0 + abs(trend_score)
            )
            notes.append("trend detected")
        elif trend_regime is TrendRegime.MEAN_REVERTING:
            position_scale *= 0.9
            parameter_overrides["mean_reversion_entry_sigma"] = max(
                1.0, 1.5 - trend_score
            )
            notes.append("mean reversion bias")
        else:
            notes.append("range-bound behaviour")

        if volatility_regime is VolatilityRegime.HIGH:
            position_scale *= 0.6
            risk_multiplier *= 0.7
            parameter_overrides["stop_loss_multiplier"] = 1.5
            notes.append("high volatility")
        elif volatility_regime is VolatilityRegime.LOW:
            position_scale *= 1.1
            risk_multiplier *= 1.05
            parameter_overrides["take_profit_multiplier"] = 0.85
            notes.append("suppressed volatility")

        if liquidity_regime is LiquidityRegime.LOW:
            position_scale *= 0.7
            risk_multiplier *= 0.8
            execution_style = "passive"
            parameter_overrides["order_slice"] = 0.5
            notes.append("thin liquidity")
        elif liquidity_regime is LiquidityRegime.HIGH:
            position_scale *= 1.05
            execution_style = "aggressive"
            notes.append("ample liquidity")

        if correlation_regime is CorrelationRegime.COUPLED:
            risk_multiplier *= 0.85
            parameter_overrides["max_gross_exposure"] = 0.8
            notes.append("assets coupled")
        elif correlation_regime is CorrelationRegime.DECOUPLED:
            parameter_overrides["max_gross_exposure"] = 1.1
            notes.append("diversified basket")

        notes.append(f"vol_score={volatility_score:.2f}")
        notes.append(f"liq_score={liquidity_score:.2f}")
        note_text = "; ".join(notes)

        return StrategyAdjustments(
            risk_multiplier=float(risk_multiplier),
            position_scale=float(position_scale),
            execution_style=execution_style,
            parameter_overrides=dict(parameter_overrides),
            notes=note_text,
        )


def _to_frame(
    data: Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series,
    *,
    name: str,
) -> pd.DataFrame:
    """Convert arbitrary tabular input into a :class:`pandas.DataFrame`."""

    if isinstance(data, pd.DataFrame):
        frame = data.copy()
    elif isinstance(data, pd.Series):
        frame = data.to_frame(name)
    else:
        frame = pd.DataFrame(data)

    frame = frame.astype(float)
    frame = frame.dropna(how="all")
    if frame.empty:
        raise ValueError(f"{name.title()} data is empty after cleaning.")
    return frame


def _to_optional_frame(
    data: Optional[Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series],
    *,
    name: str,
) -> Optional[pd.DataFrame]:
    if data is None:
        return None
    frame = _to_frame(data, name=name)
    return frame


def _robust_zscore(value: float, history: pd.Series) -> float:
    """Compute a robust z-score using the median and MAD."""

    median = float(history.median())
    mad = float((history - median).abs().median())
    if mad == 0.0:
        mad = float((history - median).abs().mean())
    if mad == 0.0:
        mad = 1e-8
    return (value - median) / mad


def _finite_quantile(values: Iterable[float], quantile: float) -> float | None:
    """Return the quantile of finite values or ``None`` when unavailable."""

    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if array.size == 0:
        return None
    quantile = float(np.clip(quantile, 0.0, 1.0))
    return float(np.quantile(array, quantile))


__all__ = [
    "CorrelationRegime",
    "DetectorConfig",
    "LiquidityRegime",
    "MarketRegimeSnapshot",
    "RegimeDetector",
    "StrategyAdjustments",
    "TrendRegime",
    "VolatilityRegime",
]
