"""Unified system validation integrator for TradePulse.

This module provides a comprehensive system-level validator that integrates
physics, neuroscience, and mathematical validation into a unified framework.
The SystemIntegrator ensures that all three foundational pillars are validated
together for complete system integrity.

Key Components:
    SystemState: Combined state snapshot including all validation domains
    SystemValidationConfig: Configuration for integrated validation
    SystemValidationReport: Comprehensive report across all domains
    SystemIntegrator: Main integrator for unified validation

The integrator provides:
    - Unified validation across physics, neuro, and mathematical domains
    - Cross-domain consistency checks
    - Aggregate health scoring
    - Real-time system monitoring support

Example:
    >>> integrator = SystemIntegrator()
    >>> state = SystemState(
    ...     thermodynamic=ThermodynamicState(free_energy=1e-18, entropy=0.5),
    ...     pathway=PathwayState(dopamine=0.5, serotonin=0.4, excitation=0.5, inhibition=0.5),
    ...     data=np.array([1.0, 2.0, 3.0])
    ... )
    >>> report = integrator.validate(state)
    >>> print(f"System health: {report.health_score:.2f}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

import numpy as np

from .mathematical_logic import DataIntegrityReport, MathematicalLogicValidator
from .neuro_integrity import (
    NeuroIntegrity,
    NeuroIntegrityConfig,
    NeuroIntegrityReport,
    PathwayState,
)
from .physics_validator import (
    EnergyBounds,
    PhysicsConstraintReport,
    PhysicsValidator,
    ThermodynamicState,
)


class SystemHealthLevel(Enum):
    """System health classification levels."""

    CRITICAL = "critical"  # Major violations, immediate action required
    WARNING = "warning"  # Minor issues, attention needed
    HEALTHY = "healthy"  # All systems nominal
    OPTIMAL = "optimal"  # All systems performing excellently


@dataclass(slots=True)
class SystemState:
    """Combined system state across all validation domains.

    Attributes:
        thermodynamic: Physics/thermodynamic state (optional)
        pathway: Neural pathway state (optional)
        data: Data array for mathematical validation (optional)
        data_name: Name for data array in reports
        market_phase: Current market phase for context
        timestamp_ms: State timestamp in milliseconds
    """

    thermodynamic: ThermodynamicState | None = None
    pathway: PathwayState | None = None
    data: np.ndarray | None = None
    data_name: str = "system_data"
    market_phase: str = "neutral"
    timestamp_ms: float | None = None


@dataclass(frozen=True, slots=True)
class SystemValidationConfig:
    """Configuration for system-level validation.

    Attributes:
        energy_bounds: Bounds for physics validation
        neuro_config: Configuration for neural validation
        data_min_value: Minimum allowed data value
        data_max_value: Maximum allowed data value
        health_thresholds: Thresholds for health level classification
        cross_domain_checks: Enable cross-domain consistency checks
        entropy_variability_threshold: Threshold for entropy-variability consistency
        ei_balance_threshold: Threshold for E/I balance cross-check
        energy_floor: Minimum energy for cross-check validation
        coherence_threshold: Coherence threshold for quality cross-check
        nan_ratio_threshold: NaN ratio threshold for quality cross-check
    """

    energy_bounds: EnergyBounds = field(default_factory=EnergyBounds)
    neuro_config: NeuroIntegrityConfig = field(default_factory=NeuroIntegrityConfig)
    data_min_value: float | None = None
    data_max_value: float | None = None
    health_thresholds: Mapping[str, float] = field(
        default_factory=lambda: {
            "critical": 0.3,
            "warning": 0.6,
            "healthy": 0.85,
        }
    )
    cross_domain_checks: bool = True
    # Cross-domain consistency thresholds
    entropy_variability_threshold: float = 0.05
    ei_balance_threshold: float = 3.0
    energy_floor: float = 1e-20
    coherence_threshold: float = 0.8
    nan_ratio_threshold: float = 0.1


@dataclass(slots=True)
class SystemValidationReport:
    """Comprehensive validation report across all domains.

    Attributes:
        is_valid: True if all domains pass validation
        health_level: Classified health level
        health_score: Aggregate health score (0.0 - 1.0)
        physics_report: Physics validation report (if applicable)
        neuro_report: Neural validation report (if applicable)
        data_report: Data validation report (if applicable)
        cross_domain_issues: Issues found in cross-domain checks
        metrics: Aggregate metrics across all domains
    """

    is_valid: bool = True
    health_level: SystemHealthLevel = SystemHealthLevel.HEALTHY
    health_score: float = 1.0
    physics_report: PhysicsConstraintReport | None = None
    neuro_report: NeuroIntegrityReport | None = None
    data_report: DataIntegrityReport | None = None
    cross_domain_issues: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def add_cross_domain_issue(self, issue: str) -> None:
        """Add a cross-domain consistency issue."""
        self.cross_domain_issues.append(issue)
        self.is_valid = False

    def summary(self) -> str:
        """Generate human-readable summary."""
        parts = [
            f"System Health: {self.health_level.value.upper()} ({self.health_score:.1%})",
            f"Valid: {self.is_valid}",
        ]
        if self.physics_report:
            parts.append(f"Physics: {'OK' if self.physics_report.is_valid else 'FAIL'}")
        if self.neuro_report:
            parts.append(f"Neuro: {'OK' if self.neuro_report.is_valid else 'FAIL'}")
        if self.data_report:
            parts.append(f"Data: {'OK' if self.data_report.is_valid else 'FAIL'}")
        if self.cross_domain_issues:
            parts.append(f"Cross-domain issues: {len(self.cross_domain_issues)}")
        return " | ".join(parts)


class SystemIntegrator:
    """Unified system validator integrating all validation domains.

    The SystemIntegrator provides comprehensive validation across physics,
    neuroscience, and mathematical domains. It ensures cross-domain consistency
    and provides aggregate health scoring for real-time monitoring.

    Example:
        >>> integrator = SystemIntegrator()
        >>> state = SystemState(
        ...     thermodynamic=ThermodynamicState(free_energy=1e-18, entropy=0.5),
        ...     pathway=PathwayState(
        ...         dopamine=0.5, serotonin=0.4, excitation=0.5, inhibition=0.5
        ...     ),
        ... )
        >>> report = integrator.validate(state)
        >>> print(f"Health: {report.health_score:.2f}")
    """

    def __init__(self, config: SystemValidationConfig | None = None) -> None:
        """Initialize the system integrator.

        Args:
            config: Configuration for validation. Uses defaults if None.
        """
        self.config = config or SystemValidationConfig()
        self.physics_validator = PhysicsValidator(self.config.energy_bounds)
        self.neuro_validator = NeuroIntegrity(self.config.neuro_config)
        self.math_validator = MathematicalLogicValidator()

    def validate(self, state: SystemState) -> SystemValidationReport:
        """Perform comprehensive system validation.

        Args:
            state: Combined system state to validate.

        Returns:
            SystemValidationReport with results from all domains.
        """
        report = SystemValidationReport()
        domain_scores: list[float] = []

        # Physics validation
        if state.thermodynamic is not None:
            physics_report = self.physics_validator.validate_state(state.thermodynamic)
            report.physics_report = physics_report
            score = 1.0 if physics_report.is_valid else 0.0
            # Adjust score based on warnings
            if physics_report.warnings:
                score = max(0.5, score - 0.1 * len(physics_report.warnings))
            domain_scores.append(score)
            report.metrics["physics_score"] = score
            report.metrics.update(
                {f"physics_{k}": v for k, v in physics_report.metrics.items()}
            )

        # Neural validation
        if state.pathway is not None:
            neuro_report = self.neuro_validator.validate_state(state.pathway)
            report.neuro_report = neuro_report
            score = 1.0 if neuro_report.is_valid else 0.0
            if neuro_report.warnings:
                score = max(0.5, score - 0.1 * len(neuro_report.warnings))
            domain_scores.append(score)
            report.metrics["neuro_score"] = score
            report.metrics.update(
                {f"neuro_{k}": v for k, v in neuro_report.metrics.items()}
            )

        # Data validation
        if state.data is not None:
            data_report = self.math_validator.validate_array(
                state.data,
                name=state.data_name,
                min_value=self.config.data_min_value,
                max_value=self.config.data_max_value,
            )
            report.data_report = data_report
            score = 1.0 if data_report.is_valid else 0.0
            if data_report.warnings > 0:
                score = max(0.5, score - 0.1 * data_report.warnings)
            domain_scores.append(score)
            report.metrics["data_score"] = score
            report.metrics.update(
                {f"data_{k}": v for k, v in data_report.metrics.items()}
            )

        # Cross-domain consistency checks
        if self.config.cross_domain_checks:
            self._check_cross_domain_consistency(state, report)

        # Compute aggregate health
        if domain_scores:
            report.health_score = float(np.mean(domain_scores))
        else:
            report.health_score = 1.0  # No domains to validate

        # Classify health level
        thresholds = self.config.health_thresholds
        if report.health_score < thresholds.get("critical", 0.3):
            report.health_level = SystemHealthLevel.CRITICAL
        elif report.health_score < thresholds.get("warning", 0.6):
            report.health_level = SystemHealthLevel.WARNING
        elif report.health_score < thresholds.get("healthy", 0.85):
            report.health_level = SystemHealthLevel.HEALTHY
        else:
            report.health_level = SystemHealthLevel.OPTIMAL

        # Update overall validity
        report.is_valid = (
            report.is_valid
            and (report.physics_report is None or report.physics_report.is_valid)
            and (report.neuro_report is None or report.neuro_report.is_valid)
            and (report.data_report is None or report.data_report.is_valid)
        )

        # Encode market phase as deterministic numeric value
        phase_mapping = {
            "neutral": 0.5,
            "bullish": 0.7,
            "bearish": 0.3,
            "volatile": 0.8,
            "stable": 0.4,
            "proto": 0.2,
            "precognitive": 0.6,
            "emergent": 0.9,
            "post-emergent": 0.1,
        }
        report.metrics["market_phase"] = phase_mapping.get(
            state.market_phase.lower(), 0.5
        )
        if state.timestamp_ms is not None:
            report.metrics["timestamp_ms"] = state.timestamp_ms

        return report

    def validate_transition(
        self,
        state_before: SystemState,
        state_after: SystemState,
        dt: float,
    ) -> SystemValidationReport:
        """Validate a system state transition.

        Args:
            state_before: Initial system state.
            state_after: Final system state.
            dt: Time delta in seconds.

        Returns:
            SystemValidationReport for the transition.
        """
        report = SystemValidationReport()
        domain_scores: list[float] = []

        # Physics transition validation
        if (
            state_before.thermodynamic is not None
            and state_after.thermodynamic is not None
        ):
            physics_report = self.physics_validator.validate_transition(
                state_before.thermodynamic, state_after.thermodynamic, dt
            )
            report.physics_report = physics_report
            score = 1.0 if physics_report.is_valid else 0.0
            domain_scores.append(score)
            report.metrics["physics_score"] = score

        # Neural transition validation
        if state_before.pathway is not None and state_after.pathway is not None:
            neuro_report = self.neuro_validator.validate_transition(
                state_before.pathway, state_after.pathway, dt
            )
            report.neuro_report = neuro_report
            score = 1.0 if neuro_report.is_valid else 0.0
            domain_scores.append(score)
            report.metrics["neuro_score"] = score

        # Validate final state data
        if state_after.data is not None:
            data_report = self.math_validator.validate_array(
                state_after.data,
                name=state_after.data_name,
                min_value=self.config.data_min_value,
                max_value=self.config.data_max_value,
            )
            report.data_report = data_report
            score = 1.0 if data_report.is_valid else 0.0
            domain_scores.append(score)
            report.metrics["data_score"] = score

        # Compute aggregate
        if domain_scores:
            report.health_score = float(np.mean(domain_scores))

        # Classify health level
        thresholds = self.config.health_thresholds
        if report.health_score < thresholds.get("critical", 0.3):
            report.health_level = SystemHealthLevel.CRITICAL
        elif report.health_score < thresholds.get("warning", 0.6):
            report.health_level = SystemHealthLevel.WARNING
        elif report.health_score < thresholds.get("healthy", 0.85):
            report.health_level = SystemHealthLevel.HEALTHY
        else:
            report.health_level = SystemHealthLevel.OPTIMAL

        report.is_valid = all(
            r is None or r.is_valid
            for r in [report.physics_report, report.neuro_report, report.data_report]
        )

        return report

    def _check_cross_domain_consistency(
        self, state: SystemState, report: SystemValidationReport
    ) -> None:
        """Check consistency between validation domains.

        Args:
            state: System state being validated.
            report: Report to add issues to.
        """
        cfg = self.config

        # Check entropy consistency between physics and data
        if (
            state.thermodynamic is not None
            and state.data is not None
            and len(state.data) > 1
        ):
            # High physical entropy should correlate with data variability
            physical_entropy = state.thermodynamic.entropy
            finite_data = state.data[np.isfinite(state.data)]
            if len(finite_data) > 0:
                data_std = float(np.std(finite_data))
                data_mean = float(np.mean(np.abs(finite_data)))

                if data_mean > 0:
                    data_cv = data_std / data_mean  # Coefficient of variation

                    # Check for inconsistency: high entropy but low variability
                    if (
                        physical_entropy > 0.7
                        and data_cv < cfg.entropy_variability_threshold
                    ):
                        report.add_cross_domain_issue(
                            f"Entropy-variability mismatch: entropy={physical_entropy:.2f}, "
                            f"data_cv={data_cv:.4f}"
                        )

        # Check neural-physics energy consistency
        if state.thermodynamic is not None and state.pathway is not None:
            # High neural excitation should correlate with higher energy state
            ei_balance = state.pathway.ei_balance
            free_energy = state.thermodynamic.free_energy

            # Extreme E/I imbalance with very low energy is suspicious
            if ei_balance > cfg.ei_balance_threshold and free_energy < cfg.energy_floor:
                report.add_cross_domain_issue(
                    f"Neural-energy mismatch: E/I={ei_balance:.2f}, energy={free_energy:.2e}"
                )

        # Check data quality vs neural coherence
        if state.pathway is not None and state.data is not None:
            coherence = state.pathway.coherence
            nan_count = int(np.sum(~np.isfinite(state.data)))
            nan_ratio = nan_count / len(state.data) if len(state.data) > 0 else 0

            # High coherence with poor data quality is concerning
            if (
                coherence > cfg.coherence_threshold
                and nan_ratio > cfg.nan_ratio_threshold
            ):
                report.add_cross_domain_issue(
                    f"Coherence-quality mismatch: coherence={coherence:.2f}, "
                    f"nan_ratio={nan_ratio:.2%}"
                )


def compute_system_health_score(
    physics_valid: bool = True,
    neuro_valid: bool = True,
    data_valid: bool = True,
    physics_warnings: int = 0,
    neuro_warnings: int = 0,
    data_warnings: int = 0,
) -> float:
    """Compute aggregate system health score.

    Args:
        physics_valid: Whether physics validation passed.
        neuro_valid: Whether neural validation passed.
        data_valid: Whether data validation passed.
        physics_warnings: Number of physics warnings.
        neuro_warnings: Number of neural warnings.
        data_warnings: Number of data warnings.

    Returns:
        Aggregate health score in [0, 1].
    """
    scores = []

    for valid, warnings in [
        (physics_valid, physics_warnings),
        (neuro_valid, neuro_warnings),
        (data_valid, data_warnings),
    ]:
        if valid:
            score = max(0.5, 1.0 - 0.1 * warnings)
        else:
            score = 0.0
        scores.append(score)

    return float(np.mean(scores))


__all__ = [
    "SystemHealthLevel",
    "SystemState",
    "SystemValidationConfig",
    "SystemValidationReport",
    "SystemIntegrator",
    "compute_system_health_score",
]
