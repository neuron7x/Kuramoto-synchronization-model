"""Portfolio risk stress testing utilities.

This module implements risk analytics tailored for institutional-grade
portfolio oversight.  It provides high-precision computations for
historical shock analysis, volatility scenario projection, Value at Risk
(VaR) and Expected Shortfall (ES) estimation, and structured reporting
for governance and regulatory workflows.

The implementation favours immutable data structures, explicit typing,
and reproducible calculations to align with best practices adopted in
production risk engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class PortfolioRiskMetrics:
    """Computed risk metrics for a specific confidence level and horizon."""

    var: float
    expected_shortfall: float
    confidence_level: float
    horizon_days: int

    def to_dict(self) -> Mapping[str, float | int]:
        return MappingProxyType(
            {
                "var": float(self.var),
                "expected_shortfall": float(self.expected_shortfall),
                "confidence_level": float(self.confidence_level),
                "horizon_days": int(self.horizon_days),
            }
        )


@dataclass(frozen=True, slots=True)
class ScenarioContribution:
    """Individual asset contribution within a stress scenario."""

    asset: str
    pnl: float


@dataclass(frozen=True, slots=True)
class StressScenario:
    """Historical or hypothetical shock applied to asset returns."""

    name: str
    shocks: Mapping[str, float]
    description: str | None = None
    reference_date: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("scenario name must be provided")
        if not self.shocks:
            raise ValueError("scenario shocks cannot be empty")


@dataclass(frozen=True, slots=True)
class StressScenarioResult:
    """Outcome of a stress scenario evaluation."""

    name: str
    pnl: float
    relative_impact: float
    contributions: tuple[ScenarioContribution, ...]
    description: str | None = None
    reference_date: datetime | None = None
    missing_assets: tuple[str, ...] = ()

    def to_dict(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "name": self.name,
                "pnl": float(self.pnl),
                "relative_impact": float(self.relative_impact),
                "description": self.description,
                "reference_date": self.reference_date.isoformat()
                if self.reference_date
                else None,
                "missing_assets": list(self.missing_assets),
                "contributions": [
                    {"asset": item.asset, "pnl": float(item.pnl)}
                    for item in self.contributions
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class VolatilityScenario:
    """Volatility stress configuration."""

    name: str
    volatility_multiplier: float
    horizon_days: int = 1
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("scenario name must be provided")
        if self.volatility_multiplier <= 0:
            raise ValueError("volatility multiplier must be positive")
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")


@dataclass(frozen=True, slots=True)
class VolatilityScenarioResult:
    """Output of a volatility stress projection."""

    name: str
    volatility_multiplier: float
    horizon_days: int
    baseline_var: float
    baseline_expected_shortfall: float
    projected_var: float
    projected_expected_shortfall: float
    description: str | None = None

    def to_dict(self) -> Mapping[str, float | int | str | None]:
        return MappingProxyType(
            {
                "name": self.name,
                "volatility_multiplier": float(self.volatility_multiplier),
                "horizon_days": int(self.horizon_days),
                "baseline_var": float(self.baseline_var),
                "baseline_expected_shortfall": float(
                    self.baseline_expected_shortfall
                ),
                "projected_var": float(self.projected_var),
                "projected_expected_shortfall": float(
                    self.projected_expected_shortfall
                ),
                "description": self.description,
            }
        )


@dataclass(frozen=True, slots=True)
class RiskLimitBreach:
    """Captured breach of a configured risk limit."""

    metric: str
    value: float
    limit: float

    def to_dict(self) -> Mapping[str, float | str]:
        return MappingProxyType(
            {"metric": self.metric, "value": float(self.value), "limit": float(self.limit)}
        )


@dataclass(frozen=True, slots=True)
class PortfolioStressReport:
    """Aggregate results for a portfolio risk stress assessment."""

    generated_at: datetime
    portfolio_value: float
    risk_metrics: PortfolioRiskMetrics
    exposures: tuple[tuple[str, float], ...]
    scenario_results: tuple[StressScenarioResult, ...]
    volatility_results: tuple[VolatilityScenarioResult, ...]
    limit_breaches: tuple[RiskLimitBreach, ...]

    def to_dict(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "generated_at": self.generated_at.isoformat(),
                "portfolio_value": float(self.portfolio_value),
                "risk_metrics": dict(self.risk_metrics.to_dict()),
                "exposures": [
                    {"asset": asset, "notional": float(amount)}
                    for asset, amount in self.exposures
                ],
                "scenario_results": [
                    dict(result.to_dict()) for result in self.scenario_results
                ],
                "volatility_results": [
                    dict(result.to_dict()) for result in self.volatility_results
                ],
                "limit_breaches": [
                    dict(breach.to_dict()) for breach in self.limit_breaches
                ],
            }
        )

    def to_markdown(self) -> str:
        """Render the report as a human-readable markdown document."""

        lines: list[str] = []
        lines.append("# Portfolio Stress Test Report")
        lines.append(f"Generated at: {self.generated_at.isoformat()}")
        lines.append("")
        lines.append("## Portfolio Summary")
        lines.append(f"- Portfolio value: ${self.portfolio_value:,.2f}")
        metrics = self.risk_metrics
        lines.append(
            "- VaR (" +
            f"{metrics.confidence_level:.2%}, {metrics.horizon_days}-day): ${metrics.var:,.2f}"
        )
        lines.append(
            "- Expected Shortfall: "
            + f"${metrics.expected_shortfall:,.2f}"
        )
        if self.limit_breaches:
            lines.append("- Limit breaches detected:")
            for breach in self.limit_breaches:
                lines.append(
                    f"  - {breach.metric}: value=${breach.value:,.2f} limit=${breach.limit:,.2f}"
                )
        else:
            lines.append("- Limit breaches detected: none")

        lines.append("")
        lines.append("## Exposures")
        lines.append("| Asset | Notional |")
        lines.append("| --- | ---: |")
        for asset, notional in self.exposures:
            lines.append(f"| {asset} | ${notional:,.2f} |")

        if self.scenario_results:
            lines.append("")
            lines.append("## Historical Shock Scenarios")
            lines.append("| Scenario | PnL | Relative Impact |")
            lines.append("| --- | ---: | ---: |")
            for result in self.scenario_results:
                lines.append(
                    "| "
                    + result.name
                    + f" | ${result.pnl:,.2f} | {result.relative_impact:.2%} |"
                )

        if self.volatility_results:
            lines.append("")
            lines.append("## Volatility Scenarios")
            lines.append(
                "| Scenario | Multiplier | Horizon (days) | Projected VaR | Projected ES |"
            )
            lines.append("| --- | ---: | ---: | ---: | ---: |")
            for result in self.volatility_results:
                lines.append(
                    "| "
                    + result.name
                    + f" | {result.volatility_multiplier:.2f} | {result.horizon_days}"
                    + f" | ${result.projected_var:,.2f} | ${result.projected_expected_shortfall:,.2f} |"
                )

        return "\n".join(lines)


class PortfolioStressTester:
    """High-precision risk stress tester for trading portfolios."""

    def __init__(
        self,
        asset_returns: pd.DataFrame,
        exposures: Mapping[str, float],
        *,
        portfolio_value: float,
        min_history: int = 60,
    ) -> None:
        if portfolio_value <= 0:
            raise ValueError("portfolio_value must be positive")
        if min_history <= 0:
            raise ValueError("min_history must be positive")
        if not exposures:
            raise ValueError("exposures cannot be empty")
        if asset_returns.empty:
            raise ValueError("asset_returns cannot be empty")

        exposures_series = pd.Series(exposures, dtype=float)
        if exposures_series.isnull().any():
            raise ValueError("exposures contain NaN values")

        columns = list(asset_returns.columns)
        missing = sorted(set(exposures_series.index).difference(columns))
        if missing:
            raise ValueError(f"missing return series for exposures: {missing}")

        aligned_returns = asset_returns.loc[:, exposures_series.index].astype(float)
        aligned_returns = aligned_returns.sort_index()
        pnl_series = (aligned_returns * exposures_series).sum(axis=1).dropna()
        if pnl_series.size < min_history:
            raise ValueError(
                "insufficient history for stable risk estimation; "
                f"received {pnl_series.size} observations, minimum is {min_history}"
            )

        self._returns = aligned_returns
        self._exposures = exposures_series
        self._pnl = pnl_series
        self._portfolio_value = float(portfolio_value)
        self._min_history = int(min_history)

    @property
    def exposures(self) -> Mapping[str, float]:
        return MappingProxyType(self._exposures.to_dict())

    @property
    def pnl_series(self) -> pd.Series:
        return self._pnl.copy()

    def _aggregate_pnl(self, horizon_days: int) -> pd.Series:
        if horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        if horizon_days == 1:
            return self._pnl
        return self._pnl.rolling(window=horizon_days).sum().dropna()

    def compute_var_es(
        self, *, confidence_level: float, horizon_days: int
    ) -> PortfolioRiskMetrics:
        if not (0.0 < confidence_level < 1.0):
            raise ValueError("confidence_level must be between 0 and 1")
        aggregated = self._aggregate_pnl(horizon_days)
        if aggregated.empty:
            raise ValueError("not enough data to compute risk metrics for horizon")

        losses = -aggregated.to_numpy(copy=True)
        var = float(np.quantile(losses, confidence_level))
        tail_mask = losses >= var
        if not np.any(tail_mask):
            raise RuntimeError("expected_shortfall tail set is empty")
        expected_shortfall = float(losses[tail_mask].mean())
        return PortfolioRiskMetrics(
            var=var,
            expected_shortfall=expected_shortfall,
            confidence_level=confidence_level,
            horizon_days=horizon_days,
        )

    def evaluate_historical_shocks(
        self, scenarios: Sequence[StressScenario], *, portfolio_value: float
    ) -> tuple[StressScenarioResult, ...]:
        if portfolio_value <= 0:
            raise ValueError("portfolio_value must be positive")
        results: list[StressScenarioResult] = []
        exposures = self._exposures
        for scenario in scenarios:
            shock_series = pd.Series(scenario.shocks, dtype=float)
            overlapping = shock_series.index.intersection(exposures.index)
            missing_assets = tuple(sorted(set(exposures.index).difference(overlapping)))
            contributions = (
                exposures.loc[overlapping] * shock_series.loc[overlapping]
            )
            pnl = float(contributions.sum())
            relative = pnl / portfolio_value
            contribution_objects = tuple(
                sorted(
                    (
                        ScenarioContribution(asset=asset, pnl=float(value))
                        for asset, value in contributions.items()
                    ),
                    key=lambda item: item.asset,
                )
            )
            results.append(
                StressScenarioResult(
                    name=scenario.name,
                    pnl=pnl,
                    relative_impact=relative,
                    contributions=contribution_objects,
                    description=scenario.description,
                    reference_date=scenario.reference_date,
                    missing_assets=missing_assets,
                )
            )
        return tuple(results)

    def evaluate_volatility_scenarios(
        self,
        scenarios: Sequence[VolatilityScenario],
        *,
        confidence_level: float,
    ) -> tuple[VolatilityScenarioResult, ...]:
        results: list[VolatilityScenarioResult] = []
        for scenario in scenarios:
            baseline = self.compute_var_es(
                confidence_level=confidence_level,
                horizon_days=scenario.horizon_days,
            )
            projected_var = baseline.var * scenario.volatility_multiplier
            projected_es = baseline.expected_shortfall * scenario.volatility_multiplier
            results.append(
                VolatilityScenarioResult(
                    name=scenario.name,
                    volatility_multiplier=scenario.volatility_multiplier,
                    horizon_days=scenario.horizon_days,
                    baseline_var=baseline.var,
                    baseline_expected_shortfall=baseline.expected_shortfall,
                    projected_var=projected_var,
                    projected_expected_shortfall=projected_es,
                    description=scenario.description,
                )
            )
        return tuple(results)

    def run(
        self,
        *,
        confidence_level: float = 0.99,
        horizon_days: int = 1,
        var_limit: float | None = None,
        expected_shortfall_limit: float | None = None,
        historical_shocks: Sequence[StressScenario] | None = None,
        volatility_scenarios: Sequence[VolatilityScenario] | None = None,
    ) -> PortfolioStressReport:
        risk_metrics = self.compute_var_es(
            confidence_level=confidence_level, horizon_days=horizon_days
        )

        scenario_results = self.evaluate_historical_shocks(
            historical_shocks or (), portfolio_value=self._portfolio_value
        )
        volatility_results = self.evaluate_volatility_scenarios(
            volatility_scenarios or (), confidence_level=confidence_level
        )

        breaches: list[RiskLimitBreach] = []
        if var_limit is not None and risk_metrics.var > var_limit:
            breaches.append(
                RiskLimitBreach(metric="var", value=risk_metrics.var, limit=var_limit)
            )
        if (
            expected_shortfall_limit is not None
            and risk_metrics.expected_shortfall > expected_shortfall_limit
        ):
            breaches.append(
                RiskLimitBreach(
                    metric="expected_shortfall",
                    value=risk_metrics.expected_shortfall,
                    limit=expected_shortfall_limit,
                )
            )

        exposures_tuple = tuple(
            sorted((asset, float(amount)) for asset, amount in self._exposures.items())
        )

        return PortfolioStressReport(
            generated_at=datetime.now(timezone.utc),
            portfolio_value=self._portfolio_value,
            risk_metrics=risk_metrics,
            exposures=exposures_tuple,
            scenario_results=scenario_results,
            volatility_results=volatility_results,
            limit_breaches=tuple(breaches),
        )


__all__ = [
    "PortfolioRiskMetrics",
    "PortfolioStressReport",
    "PortfolioStressTester",
    "RiskLimitBreach",
    "ScenarioContribution",
    "StressScenario",
    "StressScenarioResult",
    "VolatilityScenario",
    "VolatilityScenarioResult",
]

