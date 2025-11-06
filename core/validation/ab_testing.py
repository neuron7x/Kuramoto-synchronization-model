"""A/B testing protocols for validating FHMC improvements with regime-shift scenarios.

Implements measurable metrics validation as recommended in 2025 audit:
"додати A/B-протоколи: симулювати regime-shift (vol_shock>1.5), 
 міряти Sharpe↑5-10% vs. baseline"
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable

import numpy as np


class TestVariant(Enum):
    """A/B test variant identifier."""

    BASELINE = "baseline"
    TREATMENT = "treatment"


@dataclass
class PerformanceMetrics:
    """Trading performance metrics for A/B comparison."""

    sharpe_ratio: float
    max_drawdown: float
    total_return: float
    volatility: float
    calmar_ratio: float
    sortino_ratio: float
    win_rate: float
    alpha_stability: float


@dataclass
class ABTestResult:
    """Results of an A/B test comparing baseline vs treatment."""

    baseline_metrics: PerformanceMetrics
    treatment_metrics: PerformanceMetrics
    sharpe_improvement: float
    drawdown_improvement: float
    alpha_improvement: float
    statistical_significance: float
    test_passed: bool
    regime_shift_detected: bool


class RegimeShiftSimulator:
    """Simulate regime shifts for A/B testing validation.
    
    Generates vol_shock > 1.5 scenarios to test FHMC resilience.
    """

    def __init__(self, base_volatility: float = 0.02, shock_multiplier: float = 1.5) -> None:
        self.base_volatility = base_volatility
        self.shock_multiplier = shock_multiplier

    def generate_shock(self, duration: int, shock_magnitude: float | None = None) -> np.ndarray:
        """Generate volatility shock series."""
        if shock_magnitude is None:
            shock_magnitude = self.shock_multiplier
        
        # Normal regime
        normal_vol = np.ones(duration) * self.base_volatility
        
        # Inject shock in middle 20%
        shock_start = int(duration * 0.4)
        shock_end = int(duration * 0.6)
        normal_vol[shock_start:shock_end] *= shock_magnitude
        
        return normal_vol

    def detect_regime_shift(self, returns: Iterable[float], threshold: float = 1.5) -> bool:
        """Detect if regime shift occurred (vol_shock > threshold)."""
        series = np.asarray(returns, dtype=float)
        if len(series) < 60:
            return False
        
        # Rolling volatility
        window = 60
        rolling_vol = np.array([
            np.std(series[max(0, i - window):i + 1])
            for i in range(len(series))
        ])
        
        baseline_vol = np.median(rolling_vol[:len(rolling_vol) // 4])
        if baseline_vol == 0:
            return False
        
        max_vol = np.max(rolling_vol)
        vol_shock = max_vol / baseline_vol
        
        return vol_shock > threshold


class ABTestProtocol:
    """A/B testing protocol for FHMC validation with measurable metrics.
    
    Implements audit recommendation for empirical validation with:
    - Sharpe ratio improvement target: 5-10%
    - MaxDD reduction target: 15%
    - α_agent stability: [0.8, 1.0]
    """

    def __init__(
        self,
        sharpe_improvement_threshold: float = 0.05,
        drawdown_improvement_threshold: float = 0.15,
        alpha_target: tuple[float, float] = (0.8, 1.0),
        confidence_level: float = 0.95,
    ) -> None:
        self.sharpe_threshold = sharpe_improvement_threshold
        self.drawdown_threshold = drawdown_improvement_threshold
        self.alpha_target = alpha_target
        self.confidence_level = confidence_level

    def compute_metrics(
        self,
        returns: Iterable[float],
        alpha_series: Iterable[float] | None = None,
    ) -> PerformanceMetrics:
        """Compute comprehensive performance metrics."""
        ret = np.asarray(returns, dtype=float)
        
        if len(ret) < 2:
            return PerformanceMetrics(
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                total_return=0.0,
                volatility=0.0,
                calmar_ratio=0.0,
                sortino_ratio=0.0,
                win_rate=0.0,
                alpha_stability=0.0,
            )
        
        # Core metrics
        total_return = float(np.sum(ret))
        volatility = float(np.std(ret))
        sharpe = float(np.mean(ret) / (volatility + 1e-10) * np.sqrt(252))
        
        # Drawdown
        cumulative = np.cumsum(ret)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
        
        # Calmar ratio
        calmar = float(total_return / (max_dd + 1e-10))
        
        # Sortino ratio (downside deviation)
        negative_returns = ret[ret < 0]
        downside_dev = float(np.std(negative_returns)) if len(negative_returns) > 0 else volatility
        sortino = float(np.mean(ret) / (downside_dev + 1e-10) * np.sqrt(252))
        
        # Win rate
        win_rate = float(np.sum(ret > 0) / len(ret)) if len(ret) > 0 else 0.0
        
        # Alpha stability
        alpha_stability = 0.0
        if alpha_series is not None:
            alphas = np.asarray(alpha_series, dtype=float)
            if len(alphas) > 0:
                target_center = sum(self.alpha_target) / 2
                alpha_stability = float(1.0 - np.mean(np.abs(alphas - target_center)))
        
        return PerformanceMetrics(
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            total_return=total_return,
            volatility=volatility,
            calmar_ratio=calmar,
            sortino_ratio=sortino,
            win_rate=win_rate,
            alpha_stability=alpha_stability,
        )

    def statistical_test(
        self,
        baseline_returns: Iterable[float],
        treatment_returns: Iterable[float],
    ) -> float:
        """Perform statistical significance test (t-test).
        
        Returns p-value indicating statistical significance.
        """
        baseline = np.asarray(baseline_returns, dtype=float)
        treatment = np.asarray(treatment_returns, dtype=float)
        
        if len(baseline) < 2 or len(treatment) < 2:
            return 1.0
        
        # Welch's t-test (unequal variances)
        mean_diff = np.mean(treatment) - np.mean(baseline)
        var_baseline = np.var(baseline, ddof=1)
        var_treatment = np.var(treatment, ddof=1)
        
        pooled_se = np.sqrt(var_baseline / len(baseline) + var_treatment / len(treatment))
        
        if pooled_se == 0:
            return 1.0
        
        t_stat = mean_diff / pooled_se
        
        # Approximate p-value (two-tailed)
        df = min(len(baseline), len(treatment)) - 1
        # Simple approximation
        p_value = 2.0 * (1.0 - 0.5 * (1.0 + np.tanh(abs(t_stat) / np.sqrt(df))))
        
        return float(np.clip(p_value, 0.0, 1.0))

    def run_test(
        self,
        baseline_returns: Iterable[float],
        treatment_returns: Iterable[float],
        baseline_alphas: Iterable[float] | None = None,
        treatment_alphas: Iterable[float] | None = None,
    ) -> ABTestResult:
        """Run complete A/B test and determine if treatment passes.
        
        Returns ABTestResult with all metrics and pass/fail decision.
        """
        baseline_metrics = self.compute_metrics(baseline_returns, baseline_alphas)
        treatment_metrics = self.compute_metrics(treatment_returns, treatment_alphas)
        
        # Compute improvements
        sharpe_improvement = (
            (treatment_metrics.sharpe_ratio - baseline_metrics.sharpe_ratio)
            / (abs(baseline_metrics.sharpe_ratio) + 1e-10)
        )
        
        drawdown_improvement = (
            (baseline_metrics.max_drawdown - treatment_metrics.max_drawdown)
            / (baseline_metrics.max_drawdown + 1e-10)
        )
        
        alpha_improvement = (
            treatment_metrics.alpha_stability - baseline_metrics.alpha_stability
        )
        
        # Statistical significance
        p_value = self.statistical_test(baseline_returns, treatment_returns)
        
        # Regime shift detection
        regime_shift = RegimeShiftSimulator().detect_regime_shift(treatment_returns)
        
        # Pass criteria
        test_passed = (
            sharpe_improvement >= self.sharpe_threshold
            and drawdown_improvement >= self.drawdown_threshold
            and p_value < (1.0 - self.confidence_level)
        )
        
        return ABTestResult(
            baseline_metrics=baseline_metrics,
            treatment_metrics=treatment_metrics,
            sharpe_improvement=sharpe_improvement,
            drawdown_improvement=drawdown_improvement,
            alpha_improvement=alpha_improvement,
            statistical_significance=1.0 - p_value,
            test_passed=test_passed,
            regime_shift_detected=regime_shift,
        )


__all__ = [
    "ABTestProtocol",
    "ABTestResult",
    "PerformanceMetrics",
    "RegimeShiftSimulator",
    "TestVariant",
]
