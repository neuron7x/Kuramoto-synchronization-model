"""Portfolio attribution and factor analytics module.

This module provides portfolio performance decomposition utilities that
align with institutional attribution standards.  It focuses on
repeatable computations for strategy, factor, and instrument level
contributions; hedge effectiveness diagnostics; regime stability
analytics; and automated alerting for concentration risks.

The implementation prefers explicit typing, immutable data structures,
and numerically stable calculations to guarantee predictable behaviour
in production pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class AttributionBreakdown:
    """Contribution of a component to total and absolute PnL."""

    name: str
    total_pnl: float
    share_of_total: float
    share_of_abs_total: float

    def to_dict(self) -> Mapping[str, float | str]:
        return MappingProxyType(
            {
                "name": self.name,
                "total_pnl": float(self.total_pnl),
                "share_of_total": float(self.share_of_total),
                "share_of_abs_total": float(self.share_of_abs_total),
            }
        )


@dataclass(frozen=True, slots=True)
class ExposureBreakdown:
    """Average exposure for a risk bucket."""

    name: str
    exposure: float
    share_of_total: float

    def to_dict(self) -> Mapping[str, float | str]:
        return MappingProxyType(
            {
                "name": self.name,
                "exposure": float(self.exposure),
                "share_of_total": float(self.share_of_total),
            }
        )


@dataclass(frozen=True, slots=True)
class HedgeEffectivenessResult:
    """Diagnostics for a hedge relationship."""

    pair: str
    primary: str
    hedge: str
    beta: float
    effectiveness: float
    correlation: float

    def to_dict(self) -> Mapping[str, float | str]:
        return MappingProxyType(
            {
                "pair": self.pair,
                "primary": self.primary,
                "hedge": self.hedge,
                "beta": float(self.beta),
                "effectiveness": float(self.effectiveness),
                "correlation": float(self.correlation),
            }
        )


@dataclass(frozen=True, slots=True)
class RegimeMetric:
    """Per-regime stability statistics for a strategy."""

    regime: str
    mean_pnl: float
    volatility: float
    sharpe_ratio: float

    def to_dict(self) -> Mapping[str, float | str]:
        return MappingProxyType(
            {
                "regime": self.regime,
                "mean_pnl": float(self.mean_pnl),
                "volatility": float(self.volatility),
                "sharpe_ratio": float(self.sharpe_ratio),
            }
        )


@dataclass(frozen=True, slots=True)
class StrategyRegimeStability:
    """Aggregate stability diagnostics for a strategy across regimes."""

    strategy: str
    dispersion: float
    metrics: tuple[RegimeMetric, ...]

    def to_dict(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "strategy": self.strategy,
                "dispersion": float(self.dispersion),
                "metrics": [dict(metric.to_dict()) for metric in self.metrics],
            }
        )


@dataclass(frozen=True, slots=True)
class ConcentrationAlert:
    """Alert emitted when a concentration limit is breached."""

    category: str
    name: str
    metric: str
    threshold: float
    value: float
    severity: str

    def to_dict(self) -> Mapping[str, float | str]:
        return MappingProxyType(
            {
                "category": self.category,
                "name": self.name,
                "metric": self.metric,
                "threshold": float(self.threshold),
                "value": float(self.value),
                "severity": self.severity,
            }
        )


@dataclass(frozen=True, slots=True)
class PortfolioAttributionReport:
    """Immutable portfolio attribution report payload."""

    generated_at: datetime
    total_pnl: float
    strategy_breakdown: tuple[AttributionBreakdown, ...]
    factor_breakdown: tuple[AttributionBreakdown, ...]
    instrument_breakdown: tuple[AttributionBreakdown, ...]
    factor_exposures: tuple[ExposureBreakdown, ...]
    instrument_exposures: tuple[ExposureBreakdown, ...]
    hedge_effectiveness: tuple[HedgeEffectivenessResult, ...]
    regime_stability: tuple[StrategyRegimeStability, ...]
    alerts: tuple[ConcentrationAlert, ...]

    def to_dict(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "generated_at": self.generated_at.isoformat(),
                "total_pnl": float(self.total_pnl),
                "strategy_breakdown": [
                    dict(item.to_dict()) for item in self.strategy_breakdown
                ],
                "factor_breakdown": [
                    dict(item.to_dict()) for item in self.factor_breakdown
                ],
                "instrument_breakdown": [
                    dict(item.to_dict()) for item in self.instrument_breakdown
                ],
                "factor_exposures": [
                    dict(item.to_dict()) for item in self.factor_exposures
                ],
                "instrument_exposures": [
                    dict(item.to_dict()) for item in self.instrument_exposures
                ],
                "hedge_effectiveness": [
                    dict(item.to_dict()) for item in self.hedge_effectiveness
                ],
                "regime_stability": [
                    dict(item.to_dict()) for item in self.regime_stability
                ],
                "alerts": [dict(alert.to_dict()) for alert in self.alerts],
            }
        )

    def to_markdown(self) -> str:
        """Render the report as a markdown summary."""

        lines: list[str] = []
        lines.append("# Portfolio Attribution Report")
        lines.append(f"Generated at: {self.generated_at.isoformat()}")
        lines.append("")
        lines.append(f"Total PnL: ${self.total_pnl:,.2f}")

        def _render_breakdown(title: str, items: Sequence[AttributionBreakdown]) -> None:
            if not items:
                return
            lines.append("")
            lines.append(f"## {title}")
            lines.append("| Name | PnL | Share | Abs Share |")
            lines.append("| --- | ---: | ---: | ---: |")
            for item in items:
                lines.append(
                    "| "
                    f"{item.name} | ${item.total_pnl:,.2f} | {item.share_of_total:.2%}"
                    f" | {item.share_of_abs_total:.2%} |"
                )

        _render_breakdown("Strategy Contributions", self.strategy_breakdown)
        _render_breakdown("Factor Contributions", self.factor_breakdown)
        _render_breakdown("Instrument Contributions", self.instrument_breakdown)

        def _render_exposure(title: str, items: Sequence[ExposureBreakdown]) -> None:
            if not items:
                return
            lines.append("")
            lines.append(f"## {title}")
            lines.append("| Name | Exposure | Share |")
            lines.append("| --- | ---: | ---: |")
            for item in items:
                lines.append(
                    "| "
                    f"{item.name} | {item.exposure:,.6f} | {item.share_of_total:.2%} |"
                )

        _render_exposure("Factor Exposures", self.factor_exposures)
        _render_exposure("Instrument Exposures", self.instrument_exposures)

        if self.hedge_effectiveness:
            lines.append("")
            lines.append("## Hedge Effectiveness")
            lines.append("| Pair | Beta | Effectiveness | Correlation |")
            lines.append("| --- | ---: | ---: | ---: |")
            for result in self.hedge_effectiveness:
                lines.append(
                    "| "
                    f"{result.pair} | {result.beta:.3f} | {result.effectiveness:.2%}"
                    f" | {result.correlation:.2f} |"
                )

        if self.regime_stability:
            lines.append("")
            lines.append("## Regime Stability")
            for stability in self.regime_stability:
                lines.append("")
                lines.append(f"### {stability.strategy}")
                lines.append(f"Dispersion: {stability.dispersion:.6f}")
                lines.append("| Regime | Mean PnL | Volatility | Sharpe |")
                lines.append("| --- | ---: | ---: | ---: |")
                for metric in stability.metrics:
                    lines.append(
                        "| "
                        f"{metric.regime} | {metric.mean_pnl:,.6f} | {metric.volatility:,.6f}"
                        f" | {metric.sharpe_ratio:,.2f} |"
                    )

        if self.alerts:
            lines.append("")
            lines.append("## Alerts")
            lines.append("| Category | Name | Metric | Threshold | Value | Severity |")
            lines.append("| --- | --- | --- | ---: | ---: | --- |")
            for alert in self.alerts:
                lines.append(
                    "| "
                    f"{alert.category} | {alert.name} | {alert.metric}"
                    f" | {alert.threshold:.2%} | {alert.value:.2%} | {alert.severity} |"
                )

        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PortfolioAttributionConfig:
    """Configuration for portfolio attribution analytics."""

    concentration_limit: float = 0.35
    exposure_limit: float = 0.4
    min_history: int = 20

    def __post_init__(self) -> None:
        if not (0.0 < self.concentration_limit < 1.0):
            raise ValueError("concentration_limit must be between 0 and 1")
        if not (0.0 < self.exposure_limit < 1.0):
            raise ValueError("exposure_limit must be between 0 and 1")
        if self.min_history <= 0:
            raise ValueError("min_history must be positive")


class PortfolioAttributionEngine:
    """High-confidence portfolio attribution engine."""

    def __init__(
        self,
        *,
        strategy_pnl: pd.DataFrame,
        instrument_pnl: pd.DataFrame,
        factor_exposures: pd.DataFrame,
        factor_returns: pd.DataFrame,
        regime_series: pd.Series,
        hedge_pairs: Mapping[str, tuple[str, str]] | None = None,
        instrument_exposures: pd.DataFrame | None = None,
        config: PortfolioAttributionConfig | None = None,
    ) -> None:
        if strategy_pnl.empty:
            raise ValueError("strategy_pnl cannot be empty")
        if instrument_pnl.empty:
            raise ValueError("instrument_pnl cannot be empty")
        if factor_exposures.empty:
            raise ValueError("factor_exposures cannot be empty")
        if factor_returns.empty:
            raise ValueError("factor_returns cannot be empty")
        if regime_series.empty:
            raise ValueError("regime_series cannot be empty")

        self._config = config or PortfolioAttributionConfig()

        frames = [strategy_pnl, instrument_pnl, factor_exposures, factor_returns]
        if instrument_exposures is not None:
            if instrument_exposures.empty:
                raise ValueError("instrument_exposures cannot be empty if provided")
            frames.append(instrument_exposures)

        index = strategy_pnl.index
        for frame in frames[1:]:
            index = index.intersection(frame.index)
        index = index.intersection(regime_series.index)
        if index.empty:
            raise ValueError("no overlapping index between provided series")
        if index.size < self._config.min_history:
            raise ValueError(
                "insufficient history for attribution analysis; "
                f"received {index.size} observations, minimum is {self._config.min_history}"
            )

        self._strategy_pnl = strategy_pnl.loc[index].astype(float)
        self._instrument_pnl = instrument_pnl.loc[index].astype(float)
        self._factor_exposures = factor_exposures.loc[index].astype(float)
        self._factor_returns = factor_returns.loc[index].astype(float)
        self._regimes = regime_series.loc[index]
        self._instrument_exposures = (
            instrument_exposures.loc[index].astype(float)
            if instrument_exposures is not None
            else None
        )

        factor_columns = set(self._factor_exposures.columns)
        if factor_columns != set(self._factor_returns.columns):
            raise ValueError("factor_exposures and factor_returns columns must match")

        if self._instrument_exposures is not None:
            exposure_columns = set(self._instrument_exposures.columns)
            instrument_columns = set(self._instrument_pnl.columns)
            if exposure_columns != instrument_columns:
                missing = instrument_columns.difference(exposure_columns)
                extra = exposure_columns.difference(instrument_columns)
                detail = []
                if missing:
                    detail.append(
                        "missing exposures for instruments: "
                        + ", ".join(sorted(missing))
                    )
                if extra:
                    detail.append(
                        "unexpected exposure columns: " + ", ".join(sorted(extra))
                    )
                message = "instrument_exposures columns must match instrument_pnl columns"
                if detail:
                    message = f"{message} ({'; '.join(detail)})"
                raise ValueError(message)

        self._hedge_pairs = dict(hedge_pairs or {})

        if self._strategy_pnl.isnull().any().any():
            raise ValueError("strategy_pnl contains NaN values")
        if self._instrument_pnl.isnull().any().any():
            raise ValueError("instrument_pnl contains NaN values")
        if self._factor_exposures.isnull().any().any():
            raise ValueError("factor_exposures contains NaN values")
        if self._factor_returns.isnull().any().any():
            raise ValueError("factor_returns contains NaN values")
        if self._instrument_exposures is not None and self._instrument_exposures.isnull().any().any():
            raise ValueError("instrument_exposures contains NaN values")

    def _breakdown_from_dataframe(self, df: pd.DataFrame) -> tuple[AttributionBreakdown, ...]:
        totals = df.sum(axis=0)
        total_sum = float(totals.sum())
        abs_totals = totals.abs()
        abs_sum = float(abs_totals.sum())
        breakdown: list[AttributionBreakdown] = []
        for name in sorted(df.columns):
            total = float(totals[name])
            share = total / total_sum if total_sum != 0.0 else 0.0
            abs_share = float(abs_totals[name]) / abs_sum if abs_sum != 0.0 else 0.0
            breakdown.append(
                AttributionBreakdown(
                    name=name,
                    total_pnl=total,
                    share_of_total=share,
                    share_of_abs_total=abs_share,
                )
            )
        return tuple(breakdown)

    def _compute_factor_contributions(self) -> pd.DataFrame:
        aligned_returns = self._factor_returns.loc[:, self._factor_exposures.columns]
        contributions = self._factor_exposures * aligned_returns
        return contributions

    @staticmethod
    def _exposure_breakdown(series: pd.Series) -> tuple[ExposureBreakdown, ...]:
        exposures = series.abs()
        total = float(exposures.sum())
        breakdown: list[ExposureBreakdown] = []
        for name in sorted(series.index):
            value = float(series[name])
            share = exposures[name] / total if total != 0.0 else 0.0
            breakdown.append(
                ExposureBreakdown(name=name, exposure=value, share_of_total=float(share))
            )
        return tuple(breakdown)

    def _compute_factor_exposures(self) -> tuple[ExposureBreakdown, ...]:
        avg_exposure = self._factor_exposures.abs().mean(axis=0)
        return self._exposure_breakdown(avg_exposure)

    def _compute_instrument_exposures(self) -> tuple[ExposureBreakdown, ...]:
        if self._instrument_exposures is not None:
            avg_exposure = self._instrument_exposures.abs().mean(axis=0)
        else:
            avg_exposure = self._instrument_pnl.abs().mean(axis=0)
        return self._exposure_breakdown(avg_exposure)

    @staticmethod
    def _severity(value: float, threshold: float) -> str:
        if value >= threshold * 1.5:
            return "critical"
        if value >= threshold * 1.1:
            return "high"
        return "warning"

    def _detect_concentration_alerts(
        self,
        *,
        strategy_breakdown: Sequence[AttributionBreakdown],
        factor_exposures: Sequence[ExposureBreakdown],
        instrument_exposures: Sequence[ExposureBreakdown],
    ) -> tuple[ConcentrationAlert, ...]:
        alerts: list[ConcentrationAlert] = []
        limit = self._config.concentration_limit
        for item in strategy_breakdown:
            if item.share_of_abs_total > limit:
                alerts.append(
                    ConcentrationAlert(
                        category="strategy",
                        name=item.name,
                        metric="share_of_abs_pnl",
                        threshold=limit,
                        value=item.share_of_abs_total,
                        severity=self._severity(item.share_of_abs_total, limit),
                    )
                )

        exposure_limit = self._config.exposure_limit
        for bucket, items in (
            ("factor", factor_exposures),
            ("instrument", instrument_exposures),
        ):
            for item in items:
                if item.share_of_total > exposure_limit:
                    alerts.append(
                        ConcentrationAlert(
                            category=bucket,
                            name=item.name,
                            metric="exposure_share",
                            threshold=exposure_limit,
                            value=item.share_of_total,
                            severity=self._severity(item.share_of_total, exposure_limit),
                        )
                    )
        return tuple(alerts)

    def _compute_hedge_effectiveness(self) -> tuple[HedgeEffectivenessResult, ...]:
        if not self._hedge_pairs:
            return ()
        results: list[HedgeEffectivenessResult] = []
        pnl = self._strategy_pnl
        for pair_name, (primary, hedge) in sorted(self._hedge_pairs.items()):
            if primary not in pnl.columns:
                raise KeyError(f"primary strategy '{primary}' not found in strategy_pnl")
            if hedge not in pnl.columns:
                raise KeyError(f"hedge strategy '{hedge}' not found in strategy_pnl")
            primary_series = pnl[primary].to_numpy(copy=True)
            hedge_series = pnl[hedge].to_numpy(copy=True)
            hedge_var = float(np.var(hedge_series, ddof=0))
            primary_var = float(np.var(primary_series, ddof=0))
            if hedge_var == 0.0 or primary_var == 0.0:
                results.append(
                    HedgeEffectivenessResult(
                        pair=pair_name,
                        primary=primary,
                        hedge=hedge,
                        beta=0.0,
                        effectiveness=0.0,
                        correlation=0.0,
                    )
                )
                continue
            covariance = float(np.cov(primary_series, hedge_series, ddof=0)[0, 1])
            beta = covariance / hedge_var
            residual = primary_series - beta * hedge_series
            residual_var = float(np.var(residual, ddof=0))
            effectiveness = 1.0 - (residual_var / primary_var)
            effectiveness = float(np.clip(effectiveness, 0.0, 1.0))
            correlation = covariance / (np.sqrt(primary_var) * np.sqrt(hedge_var))
            correlation = float(np.clip(correlation, -1.0, 1.0))
            results.append(
                HedgeEffectivenessResult(
                    pair=pair_name,
                    primary=primary,
                    hedge=hedge,
                    beta=beta,
                    effectiveness=effectiveness,
                    correlation=correlation,
                )
            )
        return tuple(results)

    def _compute_regime_stability(self) -> tuple[StrategyRegimeStability, ...]:
        pnl = self._strategy_pnl.copy()
        pnl["__regime__"] = self._regimes
        grouped = pnl.groupby("__regime__")
        results: list[StrategyRegimeStability] = []
        for strategy in sorted(self._strategy_pnl.columns):
            metrics: list[RegimeMetric] = []
            for regime, data in grouped:
                series = data[strategy]
                mean = float(series.mean())
                volatility = float(series.std(ddof=0))
                sharpe = mean / volatility if volatility != 0.0 else 0.0
                metrics.append(
                    RegimeMetric(
                        regime=str(regime),
                        mean_pnl=mean,
                        volatility=volatility,
                        sharpe_ratio=sharpe,
                    )
                )
            dispersion = 0.0
            if metrics:
                means = np.array([metric.mean_pnl for metric in metrics], dtype=float)
                dispersion = float(np.std(means, ddof=0))
            metrics_tuple = tuple(sorted(metrics, key=lambda item: item.regime))
            results.append(
                StrategyRegimeStability(
                    strategy=strategy,
                    dispersion=dispersion,
                    metrics=metrics_tuple,
                )
            )
        return tuple(results)

    def run(self) -> PortfolioAttributionReport:
        """Execute the attribution pipeline and build the report."""

        strategy_breakdown = self._breakdown_from_dataframe(self._strategy_pnl)
        factor_contributions = self._compute_factor_contributions()
        factor_breakdown = self._breakdown_from_dataframe(factor_contributions)
        instrument_breakdown = self._breakdown_from_dataframe(self._instrument_pnl)

        factor_exposures = self._compute_factor_exposures()
        instrument_exposures = self._compute_instrument_exposures()

        alerts = self._detect_concentration_alerts(
            strategy_breakdown=strategy_breakdown,
            factor_exposures=factor_exposures,
            instrument_exposures=instrument_exposures,
        )

        hedge_effectiveness = self._compute_hedge_effectiveness()
        regime_stability = self._compute_regime_stability()

        total_pnl = float(self._strategy_pnl.values.sum())

        return PortfolioAttributionReport(
            generated_at=datetime.now(timezone.utc),
            total_pnl=total_pnl,
            strategy_breakdown=strategy_breakdown,
            factor_breakdown=factor_breakdown,
            instrument_breakdown=instrument_breakdown,
            factor_exposures=factor_exposures,
            instrument_exposures=instrument_exposures,
            hedge_effectiveness=hedge_effectiveness,
            regime_stability=regime_stability,
            alerts=alerts,
        )


__all__ = [
    "AttributionBreakdown",
    "ConcentrationAlert",
    "ExposureBreakdown",
    "HedgeEffectivenessResult",
    "PortfolioAttributionConfig",
    "PortfolioAttributionEngine",
    "PortfolioAttributionReport",
    "RegimeMetric",
    "StrategyRegimeStability",
]

