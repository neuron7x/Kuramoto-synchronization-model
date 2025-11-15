"""Advanced diagnostic and monitoring utilities for energy model analysis.

This module provides comprehensive diagnostic capabilities for the thermodynamic
energy model, including:

- Real-time energy trend analysis with forecasting
- Anomaly detection for energy spikes and unusual patterns
- Detailed breakdown visualizations
- Energy budget tracking and alerting
- Entropy decomposition analysis

These tools enable operators to understand energy dynamics, identify potential
issues early, and maintain system stability through informed decision-making.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence
import math

try:
    import numpy as np
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    np = None  # type: ignore
    stats = None  # type: ignore

from .energy_model import EnergyMetrics, EnergyValidationResult


@dataclass(frozen=True, slots=True)
class EnergyTrend:
    """Statistical summary of energy evolution over time."""
    
    mean: float
    std: float
    min: float
    max: float
    trend_slope: float
    trend_pvalue: float
    is_increasing: bool
    forecast_next: float | None = None
    
    def is_statistically_significant(self, alpha: float = 0.05) -> bool:
        """Check if the trend is statistically significant at given alpha level."""
        return self.trend_pvalue < alpha


@dataclass(frozen=True, slots=True)
class AnomalyReport:
    """Report of detected anomalies in energy measurements."""
    
    anomaly_indices: tuple[int, ...]
    z_scores: tuple[float, ...]
    threshold: float
    anomaly_count: int
    anomaly_rate: float
    
    def has_anomalies(self) -> bool:
        """Check if any anomalies were detected."""
        return self.anomaly_count > 0


@dataclass(frozen=True, slots=True)
class EnergyBreakdown:
    """Detailed breakdown of energy components and contributions."""
    
    total_free_energy: float
    internal_energy: float
    entropy_contribution: float
    temperature: float
    penalty_contributions: Mapping[str, float]
    dominant_penalty: str | None
    dominant_penalty_value: float
    
    def get_sorted_penalties(self) -> list[tuple[str, float]]:
        """Return penalties sorted by magnitude in descending order."""
        return sorted(
            self.penalty_contributions.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )


@dataclass(slots=True)
class EnergyBudget:
    """Energy budget tracker with threshold-based alerting."""
    
    budget_limit: float
    current_usage: float = 0.0
    warning_threshold: float = 0.8
    critical_threshold: float = 0.95
    history: list[float] = field(default_factory=list)
    
    def update(self, energy: float) -> None:
        """Update the current energy usage and history."""
        self.current_usage = float(energy)
        self.history.append(self.current_usage)
    
    def utilization(self) -> float:
        """Return current energy utilization as fraction of budget."""
        if self.budget_limit <= 0:
            return 0.0
        return self.current_usage / self.budget_limit
    
    def is_warning(self) -> bool:
        """Check if energy usage exceeds warning threshold."""
        return self.utilization() >= self.warning_threshold
    
    def is_critical(self) -> bool:
        """Check if energy usage exceeds critical threshold."""
        return self.utilization() >= self.critical_threshold
    
    def remaining_budget(self) -> float:
        """Return remaining energy budget."""
        return max(0.0, self.budget_limit - self.current_usage)
    
    def alert_level(self) -> str:
        """Return current alert level as string."""
        if self.is_critical():
            return "CRITICAL"
        elif self.is_warning():
            return "WARNING"
        return "NORMAL"


class EnergyDiagnostics:
    """Comprehensive diagnostic analysis for energy model evolution."""
    
    def __init__(self, enable_forecasting: bool = True):
        self._enable_forecasting = enable_forecasting and SCIPY_AVAILABLE
    
    def analyze_trend(
        self,
        results: Sequence[EnergyValidationResult],
        *,
        min_samples: int = 3,
    ) -> EnergyTrend:
        """Analyze trend in free energy over a sequence of validation results.
        
        Args:
            results: Sequence of validation results to analyze
            min_samples: Minimum number of samples required for trend analysis
            
        Returns:
            EnergyTrend object with statistical summary
            
        Raises:
            ValueError: If insufficient samples provided
        """
        if len(results) < min_samples:
            raise ValueError(
                f"Need at least {min_samples} samples for trend analysis, "
                f"got {len(results)}"
            )
        
        energies = [r.free_energy for r in results]
        mean_energy = sum(energies) / len(energies)
        
        # Calculate standard deviation
        variance = sum((e - mean_energy) ** 2 for e in energies) / len(energies)
        std_energy = math.sqrt(variance)
        
        min_energy = min(energies)
        max_energy = max(energies)
        
        # Linear regression for trend
        n = len(energies)
        x = list(range(n))
        x_mean = (n - 1) / 2.0
        y_mean = mean_energy
        
        numerator = sum((x[i] - x_mean) * (energies[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            slope = 0.0
            pvalue = 1.0
        else:
            slope = numerator / denominator
            
            # Calculate p-value using t-statistic
            if n > 2 and std_energy > 0:
                residuals = [energies[i] - (y_mean + slope * (x[i] - x_mean)) for i in range(n)]
                se_residuals = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2))
                se_slope = se_residuals / math.sqrt(denominator)
                t_stat = abs(slope / se_slope) if se_slope > 0 else 0.0
                
                # Approximate p-value using two-tailed t-test
                if SCIPY_AVAILABLE and stats is not None:
                    pvalue = 2.0 * (1.0 - stats.t.cdf(t_stat, n - 2))
                else:
                    # Conservative approximation
                    pvalue = math.exp(-t_stat) if t_stat > 0 else 1.0
            else:
                pvalue = 1.0
        
        # Forecast next value
        forecast = None
        if self._enable_forecasting and slope != 0:
            forecast = energies[-1] + slope
        
        return EnergyTrend(
            mean=mean_energy,
            std=std_energy,
            min=min_energy,
            max=max_energy,
            trend_slope=slope,
            trend_pvalue=pvalue,
            is_increasing=slope > 0,
            forecast_next=forecast,
        )
    
    def detect_anomalies(
        self,
        results: Sequence[EnergyValidationResult],
        *,
        threshold: float = 3.0,
    ) -> AnomalyReport:
        """Detect anomalous energy values using z-score method.
        
        Args:
            results: Sequence of validation results to analyze
            threshold: Z-score threshold for anomaly detection (default: 3.0)
            
        Returns:
            AnomalyReport with detected anomalies and statistics
        """
        if len(results) < 2:
            return AnomalyReport(
                anomaly_indices=(),
                z_scores=(),
                threshold=threshold,
                anomaly_count=0,
                anomaly_rate=0.0,
            )
        
        energies = [r.free_energy for r in results]
        mean_energy = sum(energies) / len(energies)
        
        variance = sum((e - mean_energy) ** 2 for e in energies) / len(energies)
        std_energy = math.sqrt(variance)
        
        if std_energy == 0:
            return AnomalyReport(
                anomaly_indices=(),
                z_scores=tuple([0.0] * len(energies)),
                threshold=threshold,
                anomaly_count=0,
                anomaly_rate=0.0,
            )
        
        z_scores = [(e - mean_energy) / std_energy for e in energies]
        anomaly_indices = [i for i, z in enumerate(z_scores) if abs(z) > threshold]
        
        return AnomalyReport(
            anomaly_indices=tuple(anomaly_indices),
            z_scores=tuple(z_scores),
            threshold=threshold,
            anomaly_count=len(anomaly_indices),
            anomaly_rate=len(anomaly_indices) / len(results),
        )
    
    def create_breakdown(
        self,
        result: EnergyValidationResult,
        *,
        temperature: float = 0.6,
    ) -> EnergyBreakdown:
        """Create detailed breakdown of energy components.
        
        Args:
            result: Validation result to analyze
            temperature: Temperature parameter used in calculation
            
        Returns:
            EnergyBreakdown with component analysis
        """
        penalties = dict(result.penalties)
        
        # Find dominant penalty
        dominant = None
        dominant_value = 0.0
        if penalties:
            dominant = max(penalties, key=lambda k: abs(penalties[k]))
            dominant_value = penalties[dominant]
        
        entropy_contribution = -temperature * result.entropy
        
        return EnergyBreakdown(
            total_free_energy=result.free_energy,
            internal_energy=result.internal_energy,
            entropy_contribution=entropy_contribution,
            temperature=temperature,
            penalty_contributions=penalties,
            dominant_penalty=dominant,
            dominant_penalty_value=dominant_value,
        )


class EntropyDecomposition:
    """Decompose entropy into per-metric stability contributions."""
    
    def __init__(self, weights: Mapping[str, float], thresholds: Mapping[str, float]):
        self._weights = dict(weights)
        self._thresholds = dict(thresholds)
        
        weight_total = sum(self._weights.values())
        self._normalized_weights = {
            name: weight / weight_total for name, weight in self._weights.items()
        }
    
    def decompose(self, metrics: EnergyMetrics) -> Mapping[str, float]:
        """Decompose entropy into per-metric stability contributions.
        
        Args:
            metrics: Energy metrics to analyze
            
        Returns:
            Mapping from metric name to stability contribution
        """
        contributions = {}
        metrics_dict = metrics.as_dict()
        
        for name, value in metrics_dict.items():
            threshold = self._thresholds.get(name, 1.0)
            if threshold <= 0:
                stability = 0.0
            else:
                ratio = value / threshold
                stability = max(0.0, 1.0 - ratio)
            
            normalized_weight = self._normalized_weights.get(name, 0.0)
            contributions[name] = stability * normalized_weight
        
        return contributions
    
    def get_stability_ranking(self, metrics: EnergyMetrics) -> list[tuple[str, float]]:
        """Return metrics ranked by stability contribution in descending order.
        
        Args:
            metrics: Energy metrics to analyze
            
        Returns:
            List of (metric_name, contribution) tuples sorted by contribution
        """
        contributions = self.decompose(metrics)
        return sorted(contributions.items(), key=lambda x: x[1], reverse=True)


__all__ = [
    "AnomalyReport",
    "EnergyBreakdown",
    "EnergyBudget",
    "EnergyDiagnostics",
    "EnergyTrend",
    "EntropyDecomposition",
]
