"""Energy Validator Module for TACL

This module implements the thermodynamic energy validation described in docs/TACL.md.
It validates that the TradePulse execution graph operates within safe energy envelope
before a rollout progresses beyond the laboratory environment.

The validator computes Helmholtz free energy:
    F = U - T·S

where:
    U = internal energy (weighted penalties from latency, coherency, resource metrics)
    T = control temperature (fixed at 0.60 for TradePulse)
    S = stability term (proportional to headroom relative to thresholds)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricThreshold:
    """Configuration for a single metric threshold."""

    name: str
    description: str
    threshold: float
    weight: float
    unit: str = ""


@dataclass(frozen=True)
class EnergyConfig:
    """Configuration for energy validation."""

    control_temperature: float = 0.60
    max_acceptable_energy: float = 1.35

    # Metric thresholds as specified in docs/TACL.md
    metrics: Tuple[MetricThreshold, ...] = field(
        default_factory=lambda: (
            MetricThreshold(
                "latency_p95", "95th percentile end-to-end latency", 85.0, 1.6, "ms"
            ),
            MetricThreshold(
                "latency_p99", "99th percentile end-to-end latency", 120.0, 1.9, "ms"
            ),
            MetricThreshold(
                "coherency_drift", "Fractional drift of shared state", 0.08, 1.2, ""
            ),
            MetricThreshold("cpu_burn", "CPU utilisation ratio", 0.75, 0.9, ""),
            MetricThreshold("mem_cost", "Memory footprint per node", 6.5, 0.8, "GiB"),
            MetricThreshold(
                "queue_depth", "Queue length at activator ingress", 32.0, 0.7, ""
            ),
            MetricThreshold(
                "packet_loss", "Control-plane packet loss ratio", 0.005, 1.4, ""
            ),
        )
    )

    def get_total_weight(self) -> float:
        """Calculate total weight of all metrics."""
        return sum(m.weight for m in self.metrics)

    def get_metric(self, name: str) -> Optional[MetricThreshold]:
        """Retrieve a metric configuration by name."""
        for metric in self.metrics:
            if metric.name == name:
                return metric
        return None


@dataclass(frozen=True)
class MetricValue:
    """A measured metric value with timestamp."""

    name: str
    value: float
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class EnergyValidationResult:
    """Result of energy validation computation."""

    free_energy: float
    internal_energy: float
    stability: float
    temperature: float
    metrics: Dict[str, float]
    penalties: Dict[str, float]
    headrooms: Dict[str, float]
    timestamp: float
    passed: bool
    threshold: float
    margin: float

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "free_energy": self.free_energy,
            "internal_energy": self.internal_energy,
            "stability": self.stability,
            "temperature": self.temperature,
            "metrics": self.metrics,
            "penalties": self.penalties,
            "headrooms": self.headrooms,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "threshold": self.threshold,
            "margin": self.margin,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class EnergyValidator:
    """Validator for thermodynamic free energy compliance.

    This class implements the energy validation logic described in docs/TACL.md,
    computing Helmholtz free energy and validating against acceptable thresholds.
    """

    def __init__(self, config: Optional[EnergyConfig] = None) -> None:
        """Initialize the energy validator.

        Args:
            config: Energy configuration. If None, uses default configuration.
        """
        self.config = config or EnergyConfig()
        self.validation_history: List[EnergyValidationResult] = []
        logger.info(
            f"EnergyValidator initialized with T={self.config.control_temperature}, "
            f"max_F={self.config.max_acceptable_energy}"
        )

    def compute_penalty(
        self,
        metric_name: str,
        value: float,
        *,
        metric_config: Optional[MetricThreshold] = None,
        total_weight: Optional[float] = None,
    ) -> Optional[Tuple[float, float]]:
        """Compute normalized penalty and headroom for a metric.

        Args:
            metric_name: Name of the metric
            value: Measured value

        Keyword Args:
            metric_config: Optional metric configuration to avoid repeated
                lookups when callers already resolved it.
            total_weight: Pre-computed total weight for efficiency.

        Returns:
            Tuple of (penalty, headroom) or ``None`` if the metric is unknown.
            - penalty: Weighted penalty contribution (0 if below threshold)
            - headroom: Fractional headroom (positive if below threshold)
        """
        metric_config = metric_config or self.config.get_metric(metric_name)
        if metric_config is None:
            logger.warning(f"Unknown metric: {metric_name}")
            return None

        threshold = metric_config.threshold
        weight = metric_config.weight
        total_weight = total_weight or self.config.get_total_weight()

        # Guard against zero/negative thresholds to avoid division by zero and
        # represent "no slack" conditions. Any positive value should count as a
        # full-weight violation; zero preserves neutrality.
        if threshold <= 0:
            penalty = (weight / total_weight) if value > 0 else 0.0
            headroom = 0.0
            return penalty, headroom

        # Compute penalty if above threshold
        if value > threshold:
            excess_ratio = (value - threshold) / threshold
            penalty = (weight / total_weight) * excess_ratio
        else:
            penalty = 0.0

        # Compute headroom
        headroom = (threshold - value) / threshold

        return penalty, headroom

    def compute_internal_energy(
        self, metrics: Dict[str, float]
    ) -> Tuple[float, Dict[str, float], Dict[str, float]]:
        """Compute internal energy U from metrics.

        Args:
            metrics: Dictionary of metric name to measured value

        Returns:
            Tuple of (internal_energy, penalties, headrooms)
        """
        base_energy = 0.0
        penalties: Dict[str, float] = {}
        headrooms: Dict[str, float] = {}

        total_weight = self.config.get_total_weight()

        for metric_name, value in metrics.items():
            metric_config = self.config.get_metric(metric_name)
            if metric_config is None:
                logger.warning(f"Unknown metric: {metric_name}")
                continue

            penalty_headroom = self.compute_penalty(
                metric_name,
                value,
                metric_config=metric_config,
                total_weight=total_weight,
            )
            if penalty_headroom is None:
                continue

            penalty, headroom = penalty_headroom
            penalties[metric_name] = penalty
            headrooms[metric_name] = headroom
            base_energy += penalty

        return base_energy, penalties, headrooms

    def compute_stability(self, headrooms: Dict[str, float]) -> float:
        """Compute stability term ``S`` from headroom values.

        The original implementation only rewarded positive headroom (metrics
        below threshold), which could overpower modest penalties and drive
        ``F`` negative even when multiple metrics violated thresholds. For
        operational readiness we need instability to *decrease* the stability
        term instead of being silently ignored. We therefore average all
        headroom values—including negative ones—to reflect the overall
        thermodynamic headroom of the system.

        Args:
            headrooms: Dictionary of metric name to headroom value. Positive
                values indicate remaining budget, negative values indicate
                deficits.

        Returns:
            Mean headroom across metrics (can be negative when violations are
            present).
        """
        if not headrooms:
            return 0.0

        return sum(headrooms.values()) / len(headrooms)

    def compute_free_energy(self, metrics: Dict[str, float]) -> EnergyValidationResult:
        """Compute Helmholtz free energy F = U - T·S.

        Args:
            metrics: Dictionary of metric name to measured value

        Returns:
            EnergyValidationResult with all computed values
        """
        # Compute internal energy and derived values
        internal_energy, penalties, headrooms = self.compute_internal_energy(metrics)

        # Compute stability from headroom
        stability = self.compute_stability(headrooms)

        # Compute free energy: F = U - T·S
        temperature = self.config.control_temperature
        free_energy = internal_energy - temperature * stability

        # Check if validation passes
        threshold = self.config.max_acceptable_energy
        passed = free_energy <= threshold
        margin = threshold - free_energy

        result = EnergyValidationResult(
            free_energy=free_energy,
            internal_energy=internal_energy,
            stability=stability,
            temperature=temperature,
            metrics=metrics.copy(),
            penalties=penalties,
            headrooms=headrooms,
            timestamp=time.time(),
            passed=passed,
            threshold=threshold,
            margin=margin,
        )

        # Store in history
        self.validation_history.append(result)

        # Log result
        status = "PASS" if passed else "FAIL"
        logger.info(
            f"Energy validation {status}: F={free_energy:.4f}, "
            f"U={internal_energy:.4f}, S={stability:.4f}, "
            f"threshold={threshold:.4f}, margin={margin:.4f}"
        )

        return result

    def validate(self, metrics: Dict[str, float]) -> bool:
        """Validate that metrics meet energy requirements.

        Args:
            metrics: Dictionary of metric name to measured value

        Returns:
            True if validation passes, False otherwise
        """
        result = self.compute_free_energy(metrics)
        return result.passed

    def export_validation_report(self, output_path: Path) -> None:
        """Export validation results to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        if not self.validation_history:
            logger.warning("No validation history to export")
            return

        report = {
            "config": {
                "control_temperature": self.config.control_temperature,
                "max_acceptable_energy": self.config.max_acceptable_energy,
                "metrics": [
                    {
                        "name": m.name,
                        "description": m.description,
                        "threshold": m.threshold,
                        "weight": m.weight,
                        "unit": m.unit,
                    }
                    for m in self.config.metrics
                ],
            },
            "validation_history": [
                result.to_dict() for result in self.validation_history
            ],
            "summary": {
                "total_validations": len(self.validation_history),
                "passed": sum(1 for r in self.validation_history if r.passed),
                "failed": sum(1 for r in self.validation_history if not r.passed),
                "latest_free_energy": self.validation_history[-1].free_energy,
                "latest_passed": self.validation_history[-1].passed,
            },
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Validation report exported to {output_path}")

    def get_latest_result(self) -> Optional[EnergyValidationResult]:
        """Get the most recent validation result.

        Returns:
            Latest EnergyValidationResult or None if no validations performed
        """
        if not self.validation_history:
            return None
        return self.validation_history[-1]

    def clear_history(self) -> None:
        """Clear validation history."""
        self.validation_history.clear()
        logger.info("Validation history cleared")


__all__ = [
    "EnergyValidator",
    "EnergyConfig",
    "MetricThreshold",
    "MetricValue",
    "EnergyValidationResult",
]
