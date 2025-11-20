"""Performance analytics helpers for backtest results."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
from numpy.typing import NDArray
from scipy import stats

_PERIODS_PER_YEAR = 252
_DEFAULT_ALPHA = 0.05


def _to_numpy(
    array: Iterable[float] | NDArray[np.float64] | None,
) -> NDArray[np.float64]:
    if array is None:
        return np.array([], dtype=float)
    if isinstance(array, np.ndarray):
        return array.astype(float, copy=False)
    return np.asarray(list(array), dtype=float)


@dataclass(slots=True)
class PerformanceReport:
    """Collection of performance statistics for a backtest run."""

    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    probabilistic_sharpe_ratio: float | None = None
    sharpe_p_value: float | None = None
    certainty_equivalent: float | None = None
    cagr: float | None = None
    max_drawdown: float | None = None
    expected_shortfall: float | None = None
    turnover: float | None = None
    hit_ratio: float | None = None
    alpha: float | None = None
    beta: float | None = None
    information_ratio: float | None = None
    tracking_error: float | None = None

    @staticmethod
    def _clean(value: float | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)

    def as_dict(self) -> dict[str, float | None]:
        """Return a JSON-serialisable dictionary representation."""

        return {
            "sharpe_ratio": self._clean(self.sharpe_ratio),
            "sortino_ratio": self._clean(self.sortino_ratio),
            "probabilistic_sharpe_ratio": self._clean(self.probabilistic_sharpe_ratio),
            "sharpe_p_value": self._clean(self.sharpe_p_value),
            "certainty_equivalent": self._clean(self.certainty_equivalent),
            "cagr": self._clean(self.cagr),
            "max_drawdown": self._clean(self.max_drawdown),
            "expected_shortfall": self._clean(self.expected_shortfall),
            "turnover": self._clean(self.turnover),
            "hit_ratio": self._clean(self.hit_ratio),
            "alpha": self._clean(self.alpha),
            "beta": self._clean(self.beta),
            "information_ratio": self._clean(self.information_ratio),
            "tracking_error": self._clean(self.tracking_error),
        }


def compute_performance_metrics(
    *,
    equity_curve: Iterable[float] | NDArray[np.float64] | None,
    pnl: Iterable[float] | NDArray[np.float64] | None = None,
    position_changes: Iterable[float] | NDArray[np.float64] | None = None,
    initial_capital: float,
    max_drawdown: float | None = None,
    periods_per_year: int = _PERIODS_PER_YEAR,
    risk_free_rate: float = 0.0,
    alpha: float = _DEFAULT_ALPHA,
    benchmark_returns: Iterable[float] | NDArray[np.float64] | None = None,
    psr_target: float = 0.0,
    risk_aversion: float = 1.0,
) -> PerformanceReport:
    """Compute a :class:`PerformanceReport` from backtest series."""

    equity = _to_numpy(equity_curve)
    pnl_array = _to_numpy(pnl)
    position_delta = _to_numpy(position_changes)

    if pnl_array.size == 0 and equity.size:
        previous_equity = np.concatenate(([float(initial_capital)], equity[:-1]))
        pnl_array = equity - previous_equity

    returns = np.array([], dtype=float)
    if equity.size:
        previous_equity = np.concatenate(([float(initial_capital)], equity[:-1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            returns = (equity - previous_equity) / previous_equity
        returns = returns[np.isfinite(returns)]

    annualisation = math.sqrt(periods_per_year) if periods_per_year > 0 else 1.0
    excess_rate = risk_free_rate / periods_per_year if periods_per_year > 0 else 0.0

    sharpe_ratio: float | None = None
    probabilistic_sharpe_ratio: float | None = None
    sharpe_p_value: float | None = None
    if returns.size:
        # Compute excess returns with float64 precision
        # Critical for small excess returns where precision matters
        excess_returns = returns.astype(np.float64, copy=False) - excess_rate
        
        # Use float64 accumulation for mean (prevents drift for long backtests)
        mean_excess = float(np.mean(excess_returns, dtype=np.float64)) if excess_returns.size else 0.0
        
        # Compute volatility (standard deviation) with ddof=1 for sample estimate
        # Using float64 prevents precision loss in variance calculation
        volatility = (
            float(np.std(excess_returns, ddof=1, dtype=np.float64))
            if excess_returns.size > 1
            else float(np.std(excess_returns, dtype=np.float64))
        )
        
        if volatility > 0:
            # Sharpe ratio: (mean excess return) / (volatility)
            sr_periodic = mean_excess / volatility
            sharpe_ratio = sr_periodic * annualisation
            
            n_obs = excess_returns.size
            if n_obs > 1:
                # t-statistic for testing SR != 0
                t_stat = sr_periodic * math.sqrt(n_obs)
                sharpe_p_value = float(2.0 * stats.t.sf(abs(t_stat), n_obs - 1))

                # Probabilistic Sharpe Ratio (Bailey & de Prado, 2012)
                # Accounts for higher moments (skewness, kurtosis) in SR distribution
                centered = excess_returns - mean_excess
                
                # Compute moments with float64 for numerical stability
                # m2 = E[(X - μ)²], m3 = E[(X - μ)³], m4 = E[(X - μ)⁴]
                m2 = float(np.mean(centered**2, dtype=np.float64)) if centered.size else 0.0
                
                if m2 > 1e-12:
                    m3 = float(np.mean(centered**3, dtype=np.float64))
                    m4 = float(np.mean(centered**4, dtype=np.float64))
                    
                    # Standardized skewness and excess kurtosis
                    # Skewness: γ₁ = m₃ / σ³
                    # Kurtosis: γ₂ = m₄ / σ⁴ (excess kurtosis = γ₂ - 3)
                    skewness = m3 / (m2**1.5) if m2 > 0 else 0.0
                    kurtosis = m4 / (m2**2) if m2 > 0 else 3.0
                    
                    # Denominator for PSR calculation
                    # Accounts for non-normality via skewness and kurtosis adjustments
                    denom_term = (
                        1.0
                        - skewness * sr_periodic
                        + ((kurtosis - 1.0) / 4.0) * sr_periodic**2
                    )
                    
                    if denom_term > 1e-12:
                        # Z-score for PSR
                        # PSR = P[SR_estimated > SR_target | skewness, kurtosis]
                        z_score = (
                            (sr_periodic - psr_target)
                            * math.sqrt(n_obs - 1)
                            / math.sqrt(denom_term)
                        )
                        probabilistic_sharpe_ratio = float(stats.norm.cdf(z_score))

    sortino_ratio: float | None = None
    if returns.size:
        # Sortino ratio: like Sharpe but only penalizes downside volatility
        # More appropriate for strategies with asymmetric returns
        excess_returns = returns.astype(np.float64, copy=False) - excess_rate
        
        # Extract downside returns (negative excess returns only)
        downside = excess_returns[excess_returns < 0.0]
        
        if downside.size:
            # Compute downside deviation (semi-deviation)
            # Uses only negative returns to compute volatility
            downside_vol = (
                float(np.std(downside, ddof=1, dtype=np.float64))
                if downside.size > 1
                else float(np.std(downside, dtype=np.float64))
            )
            
            if downside_vol > 0:
                # Sortino = mean(excess returns) / downside_deviation
                mean_excess = float(np.mean(excess_returns, dtype=np.float64))
                sortino_ratio = (mean_excess / downside_vol) * annualisation
        elif excess_returns.size:
            # No downside deviation: all returns are non-negative
            # Sortino ratio is infinite (perfect risk-adjusted return)
            sortino_ratio = math.inf

    certainty_equivalent: float | None = None
    if returns.size:
        # Certainty Equivalent Return (CER): utility-adjusted return
        # CER = μ - (γ/2) * σ² where γ is risk aversion coefficient
        # Represents the guaranteed return an investor would accept
        # instead of the risky portfolio return distribution
        
        # Compute variance with ddof=1 for sample estimate
        # Use float64 to prevent precision loss
        variance = (
            float(np.var(returns, ddof=1, dtype=np.float64))
            if returns.size > 1
            else float(np.var(returns, dtype=np.float64))
        )
        
        mean_return = float(np.mean(returns, dtype=np.float64))
        
        # Risk aversion parameter: typically γ ∈ [1, 10]
        # γ = 1: risk-neutral, γ > 1: risk-averse
        risk_aversion_coef = float(max(risk_aversion, 0.0))
        
        # CER in periodic units (same as returns)
        ce_periodic = mean_return - 0.5 * risk_aversion_coef * variance
        
        if periods_per_year > 0:
            # Annualize CER: (1 + ce_periodic)^periods_per_year - 1
            base = 1.0 + ce_periodic
            if base <= 0.0:
                # Negative annualized return
                certainty_equivalent = -1.0
            else:
                exponent = periods_per_year * math.log(base)
                finfo = np.finfo(float)
                if exponent > math.log(finfo.max):
                    certainty_equivalent = math.inf
                elif exponent < math.log(finfo.tiny):
                    certainty_equivalent = -1.0
                else:
                    certainty_equivalent = float(math.expm1(exponent))
        else:
            certainty_equivalent = ce_periodic

    cagr: float | None = None
    if (
        equity.size
        and initial_capital > 0.0
        and equity[-1] > 0.0
        and periods_per_year > 0
    ):
        years = equity.size / periods_per_year
        if years > 0:
            cagr = float((equity[-1] / float(initial_capital)) ** (1.0 / years) - 1.0)

    if max_drawdown is None and equity.size:
        peaks = np.maximum.accumulate(equity)
        drawdowns = equity - peaks
        max_drawdown = float(drawdowns.min()) if drawdowns.size else 0.0

    expected_shortfall: float | None = None
    if returns.size:
        alpha = float(np.clip(alpha, 1e-4, 0.5))
        var_threshold = float(np.quantile(returns, alpha))
        tail_losses = returns[returns <= var_threshold]
        if tail_losses.size:
            expected_shortfall = float(np.mean(tail_losses))

    turnover: float | None = None
    if position_delta.size:
        turnover = float(np.nansum(np.abs(position_delta)))

    hit_ratio: float | None = None
    if pnl_array.size:
        wins = int(np.count_nonzero(pnl_array > 0.0))
        activity = int(np.count_nonzero(np.abs(pnl_array) > 1e-12))
        if activity > 0:
            hit_ratio = wins / activity

    alpha_value: float | None = None
    beta_value: float | None = None
    information_ratio: float | None = None
    tracking_error: float | None = None
    benchmark_array = _to_numpy(benchmark_returns)
    if returns.size and benchmark_array.size:
        m = min(returns.size, benchmark_array.size)
        port_ret = returns[-m:]
        bench_ret = benchmark_array[-m:]
        mask = np.isfinite(port_ret) & np.isfinite(bench_ret)
        port_ret = port_ret[mask]
        bench_ret = bench_ret[mask]
        if port_ret.size and bench_ret.size:
            bench_excess = bench_ret - excess_rate
            port_excess = port_ret - excess_rate
            bench_var = (
                float(np.var(bench_excess, ddof=1))
                if bench_excess.size > 1
                else float(np.var(bench_excess))
            )
            if bench_var > 1e-12:
                cov = (
                    float(np.cov(port_excess, bench_excess, ddof=1)[0, 1])
                    if port_excess.size > 1
                    else 0.0
                )
                beta_value = cov / bench_var if bench_excess.size > 1 else 0.0
            if beta_value is not None:
                alpha_periodic = float(
                    np.mean(port_excess) - (beta_value or 0.0) * np.mean(bench_excess)
                )
                alpha_value = alpha_periodic * periods_per_year
            active_returns = port_excess - bench_excess
            if active_returns.size:
                tracking_error = (
                    float(np.std(active_returns, ddof=1))
                    if active_returns.size > 1
                    else float(np.std(active_returns))
                )
                if tracking_error > 1e-12:
                    information_ratio = (
                        float(np.mean(active_returns)) / tracking_error * annualisation
                    )

    return PerformanceReport(
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        probabilistic_sharpe_ratio=probabilistic_sharpe_ratio,
        sharpe_p_value=sharpe_p_value,
        certainty_equivalent=certainty_equivalent,
        cagr=cagr,
        max_drawdown=max_drawdown,
        expected_shortfall=expected_shortfall,
        turnover=turnover,
        hit_ratio=hit_ratio,
        alpha=alpha_value,
        beta=beta_value,
        information_ratio=information_ratio,
        tracking_error=tracking_error,
    )


def export_performance_report(
    strategy_name: str,
    report: PerformanceReport,
    *,
    directory: Path | str = Path("reports"),
) -> Path:
    """Serialise a performance report to the reports directory."""

    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(
        c if c.isalnum() or c in {"-", "_"} else "_" for c in strategy_name
    ).strip("_")
    if not safe_name:
        safe_name = "strategy"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"backtest_{safe_name}_{timestamp}.json"
    path = target_dir / filename

    payload = {
        "strategy": strategy_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "performance": report.as_dict(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


__all__ = [
    "PerformanceReport",
    "compute_performance_metrics",
    "export_performance_report",
]
