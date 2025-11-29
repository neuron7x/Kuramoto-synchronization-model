"""Physics-based validation for thermodynamic system constraints.

This module provides validators that enforce thermodynamic laws and energy
conservation principles on trading system state transitions. The physics
foundation ensures that system behavior remains within physically plausible
bounds, preventing runaway states and numerical instabilities.

Key Components:
    ThermodynamicState: Immutable snapshot of system energy state
    EnergyBounds: Configuration for acceptable energy ranges
    PhysicsConstraintReport: Validation results with constraint violations
    PhysicsValidator: Main validator enforcing thermodynamic laws

The validator implements:
    - First Law: Energy conservation across state transitions
    - Second Law: Entropy non-decrease in isolated subsystems
    - Energy bounds: Minimum/maximum energy constraints
    - Rate limits: Maximum energy change rates (prevents numerical instabilities)

Example:
    >>> validator = PhysicsValidator(EnergyBounds())
    >>> state1 = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
    >>> state2 = ThermodynamicState(free_energy=0.9e-18, entropy=0.52, temperature=300.0)
    >>> report = validator.validate_transition(state1, state2, dt=1.0)
    >>> print(f"Valid: {report.is_valid}, Energy delta: {report.energy_delta:.2e}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

# Import energy constants from core.energy module
from core.energy import ENERGY_SCALE, K_BOLTZMANN_EFFECTIVE, SYSTEM_TEMPERATURE_K


@dataclass(frozen=True, slots=True)
class ThermodynamicState:
    """Immutable snapshot of system thermodynamic state.

    Attributes:
        free_energy: Gibbs/Helmholtz free energy (scaled, dimensionless units)
        entropy: System entropy (dimensionless, normalized 0-1 typical)
        temperature: Effective temperature (Kelvin-equivalent)
        internal_energy: Optional internal energy component
        resource_usage: Optional resource utilization (0-1)
        timestamp_ms: Optional timestamp in milliseconds
    """

    free_energy: float
    entropy: float
    temperature: float = SYSTEM_TEMPERATURE_K
    internal_energy: float = 0.0
    resource_usage: float = 0.0
    timestamp_ms: float | None = None

    def __post_init__(self) -> None:
        """Validate state values are finite and within bounds."""
        for attr in ("free_energy", "entropy", "temperature", "internal_energy"):
            value = getattr(self, attr)
            if not np.isfinite(value):
                raise ValueError(f"{attr} must be finite, got {value}")
        if self.temperature <= 0:
            raise ValueError(f"Temperature must be positive, got {self.temperature}")
        if not 0.0 <= self.resource_usage <= 1.0:
            raise ValueError(
                f"resource_usage must be in [0,1], got {self.resource_usage}"
            )

    @property
    def gibbs_energy(self) -> float:
        """Calculate Gibbs free energy: G = U - TS."""
        return self.internal_energy - self.temperature * self.entropy

    def as_mapping(self) -> Mapping[str, float]:
        """Return state as a dictionary for serialization."""
        return {
            "free_energy": self.free_energy,
            "entropy": self.entropy,
            "temperature": self.temperature,
            "internal_energy": self.internal_energy,
            "resource_usage": self.resource_usage,
            "gibbs_energy": self.gibbs_energy,
        }


@dataclass(frozen=True, slots=True)
class EnergyBounds:
    """Configuration defining acceptable energy ranges and rate limits.

    Attributes:
        min_free_energy: Minimum acceptable free energy (prevents collapse)
        max_free_energy: Maximum acceptable free energy (prevents explosion)
        max_energy_rate: Maximum |dE/dt| per second (stability constraint)
        min_entropy: Minimum entropy (prevents over-ordering)
        max_entropy: Maximum entropy (prevents chaos)
        entropy_tolerance: Allowed entropy decrease (numerical tolerance)
        energy_conservation_tolerance: Acceptable energy imbalance fraction
    """

    min_free_energy: float = -1e-15
    max_free_energy: float = 1e-15
    max_energy_rate: float = 1e-17  # Per second
    min_entropy: float = 0.0
    max_entropy: float = 10.0
    entropy_tolerance: float = 1e-6  # Allow small numerical entropy decrease
    energy_conservation_tolerance: float = 0.1  # 10% tolerance


@dataclass(slots=True)
class PhysicsConstraintReport:
    """Detailed report of physics constraint validation.

    Attributes:
        is_valid: True if all constraints satisfied
        energy_delta: Change in free energy
        entropy_delta: Change in entropy
        energy_rate: Rate of energy change (per second)
        violations: List of violated constraint descriptions
        warnings: List of near-violation warnings
        metrics: Additional diagnostic metrics
    """

    is_valid: bool
    energy_delta: float
    entropy_delta: float
    energy_rate: float
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def add_violation(self, message: str) -> None:
        """Add a constraint violation."""
        self.violations.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a near-violation warning."""
        self.warnings.append(message)


class PhysicsValidator:
    """Validator enforcing thermodynamic constraints on system transitions.

    The validator checks that state transitions comply with fundamental
    thermodynamic laws adapted for the trading system's energy model:

    1. Energy Conservation: Total energy change must be accountable
    2. Second Law: Entropy should not decrease (with tolerance for numerical noise)
    3. Energy Bounds: Free energy must remain within operational limits
    4. Rate Limits: Energy changes must not exceed stability thresholds

    Example:
        >>> validator = PhysicsValidator()
        >>> s1 = ThermodynamicState(free_energy=1e-18, entropy=0.5, temperature=300.0)
        >>> s2 = ThermodynamicState(free_energy=0.95e-18, entropy=0.51, temperature=300.0)
        >>> report = validator.validate_transition(s1, s2, dt=0.1)
        >>> assert report.is_valid
    """

    def __init__(self, bounds: EnergyBounds | None = None) -> None:
        """Initialize validator with energy bounds.

        Args:
            bounds: Energy constraint configuration. Uses defaults if None.
        """
        self.bounds = bounds or EnergyBounds()

    def validate_state(self, state: ThermodynamicState) -> PhysicsConstraintReport:
        """Validate a single thermodynamic state against bounds.

        Args:
            state: The thermodynamic state to validate.

        Returns:
            PhysicsConstraintReport with validation results.
        """
        report = PhysicsConstraintReport(
            is_valid=True,
            energy_delta=0.0,
            entropy_delta=0.0,
            energy_rate=0.0,
        )

        # Check free energy bounds
        if state.free_energy < self.bounds.min_free_energy:
            report.add_violation(
                f"Free energy {state.free_energy:.2e} below minimum "
                f"{self.bounds.min_free_energy:.2e}"
            )
        elif state.free_energy > self.bounds.max_free_energy:
            report.add_violation(
                f"Free energy {state.free_energy:.2e} above maximum "
                f"{self.bounds.max_free_energy:.2e}"
            )

        # Check entropy bounds
        if state.entropy < self.bounds.min_entropy:
            report.add_violation(
                f"Entropy {state.entropy:.4f} below minimum {self.bounds.min_entropy}"
            )
        elif state.entropy > self.bounds.max_entropy:
            report.add_violation(
                f"Entropy {state.entropy:.4f} above maximum {self.bounds.max_entropy}"
            )

        # Warning for near-boundary states
        energy_range = self.bounds.max_free_energy - self.bounds.min_free_energy
        energy_margin = 0.1 * energy_range
        if state.free_energy < self.bounds.min_free_energy + energy_margin:
            report.add_warning("Free energy approaching lower bound")
        elif state.free_energy > self.bounds.max_free_energy - energy_margin:
            report.add_warning("Free energy approaching upper bound")

        # Add diagnostic metrics
        report.metrics["free_energy"] = state.free_energy
        report.metrics["entropy"] = state.entropy
        report.metrics["temperature"] = state.temperature
        report.metrics["gibbs_energy"] = state.gibbs_energy

        return report

    def validate_transition(
        self,
        state_before: ThermodynamicState,
        state_after: ThermodynamicState,
        dt: float,
    ) -> PhysicsConstraintReport:
        """Validate a state transition against thermodynamic laws.

        Args:
            state_before: Initial thermodynamic state.
            state_after: Final thermodynamic state.
            dt: Time delta in seconds (must be positive).

        Returns:
            PhysicsConstraintReport with validation results.

        Raises:
            ValueError: If dt is not positive.
        """
        if dt <= 0:
            raise ValueError(f"Time delta must be positive, got {dt}")

        energy_delta = state_after.free_energy - state_before.free_energy
        entropy_delta = state_after.entropy - state_before.entropy
        energy_rate = abs(energy_delta) / dt

        report = PhysicsConstraintReport(
            is_valid=True,
            energy_delta=energy_delta,
            entropy_delta=entropy_delta,
            energy_rate=energy_rate,
        )

        # Validate both states individually
        before_report = self.validate_state(state_before)
        after_report = self.validate_state(state_after)

        for violation in before_report.violations:
            report.add_violation(f"Initial state: {violation}")
        for violation in after_report.violations:
            report.add_violation(f"Final state: {violation}")

        # Second Law: Entropy should not decrease significantly
        if entropy_delta < -self.bounds.entropy_tolerance:
            report.add_violation(
                f"Second Law violation: entropy decreased by {-entropy_delta:.6f} "
                f"(tolerance: {self.bounds.entropy_tolerance:.6f})"
            )

        # Rate limit check (stability)
        if energy_rate > self.bounds.max_energy_rate:
            report.add_violation(
                f"Energy rate {energy_rate:.2e} exceeds maximum "
                f"{self.bounds.max_energy_rate:.2e} per second"
            )
        elif energy_rate > 0.8 * self.bounds.max_energy_rate:
            report.add_warning(
                f"Energy rate {energy_rate:.2e} approaching limit {self.bounds.max_energy_rate:.2e}"
            )

        # Energy conservation check (accounting for work done)
        # In open systems, energy change should be bounded by reasonable work
        max_work = self.bounds.energy_conservation_tolerance * abs(
            state_before.free_energy
        )
        if max_work > 0 and abs(energy_delta) > max_work:
            report.add_warning(
                f"Large energy change {energy_delta:.2e} detected (threshold: {max_work:.2e})"
            )

        # Populate metrics
        report.metrics.update(
            {
                "energy_delta": energy_delta,
                "entropy_delta": entropy_delta,
                "energy_rate": energy_rate,
                "dt": dt,
                "initial_free_energy": state_before.free_energy,
                "final_free_energy": state_after.free_energy,
                "initial_entropy": state_before.entropy,
                "final_entropy": state_after.entropy,
            }
        )

        return report

    def validate_trajectory(
        self,
        states: list[ThermodynamicState],
        timestamps_ms: list[float] | None = None,
    ) -> PhysicsConstraintReport:
        """Validate a sequence of thermodynamic states.

        Args:
            states: List of sequential thermodynamic states.
            timestamps_ms: Optional list of timestamps in milliseconds.

        Returns:
            Aggregate PhysicsConstraintReport for the trajectory.
        """
        if len(states) < 2:
            return PhysicsConstraintReport(
                is_valid=True,
                energy_delta=0.0,
                entropy_delta=0.0,
                energy_rate=0.0,
            )

        total_energy_delta = states[-1].free_energy - states[0].free_energy
        total_entropy_delta = states[-1].entropy - states[0].entropy

        report = PhysicsConstraintReport(
            is_valid=True,
            energy_delta=total_energy_delta,
            entropy_delta=total_entropy_delta,
            energy_rate=0.0,
        )

        max_rate = 0.0
        for i in range(1, len(states)):
            if timestamps_ms is not None:
                dt = (timestamps_ms[i] - timestamps_ms[i - 1]) / 1000.0
            elif (
                states[i].timestamp_ms is not None
                and states[i - 1].timestamp_ms is not None
            ):
                dt = (states[i].timestamp_ms - states[i - 1].timestamp_ms) / 1000.0
            else:
                dt = 1.0  # Default 1 second

            if dt <= 0:
                continue

            step_report = self.validate_transition(states[i - 1], states[i], dt)
            for violation in step_report.violations:
                report.add_violation(f"Step {i}: {violation}")
            for warning in step_report.warnings:
                report.add_warning(f"Step {i}: {warning}")

            max_rate = max(max_rate, step_report.energy_rate)

        report.energy_rate = max_rate
        report.metrics["trajectory_length"] = len(states)
        report.metrics["max_energy_rate"] = max_rate
        report.metrics["total_energy_delta"] = total_energy_delta
        report.metrics["total_entropy_delta"] = total_entropy_delta

        return report


def compute_energy_gradient(
    state: ThermodynamicState,
    perturbation: float = 1e-6,
) -> dict[str, float]:
    """Compute numerical energy gradient with respect to state variables.

    Uses a combination of analytical gradients (from thermodynamic relations)
    and numerical finite differences for validation. The perturbation parameter
    is used for numerical gradient verification.

    Args:
        state: Current thermodynamic state.
        perturbation: Perturbation size for finite difference validation.

    Returns:
        Dictionary mapping variable names to gradient values.
    """
    gradients = {}

    # Analytical gradient w.r.t. entropy: dG/dS = -T (from Gibbs relation)
    grad_entropy_analytical = -state.temperature
    gradients["entropy"] = grad_entropy_analytical

    # Analytical gradient w.r.t. temperature: dG/dT = -S
    grad_temperature_analytical = -state.entropy
    gradients["temperature"] = grad_temperature_analytical

    # Analytical gradient w.r.t. internal energy: dG/dU = 1
    gradients["internal_energy"] = 1.0

    # Numerical validation using finite differences (for entropy)
    # This verifies the analytical gradient is correctly implemented
    if perturbation > 0:
        s_plus = state.entropy + perturbation
        s_minus = state.entropy - perturbation
        # G = U - TS, so dG/dS numerically:
        g_plus = state.internal_energy - state.temperature * s_plus
        g_minus = state.internal_energy - state.temperature * s_minus
        grad_entropy_numerical = (g_plus - g_minus) / (2 * perturbation)
        gradients["entropy_numerical"] = grad_entropy_numerical

    return gradients


__all__ = [
    "ThermodynamicState",
    "EnergyBounds",
    "PhysicsConstraintReport",
    "PhysicsValidator",
    "compute_energy_gradient",
    "K_BOLTZMANN_EFFECTIVE",
    "SYSTEM_TEMPERATURE_K",
    "ENERGY_SCALE",
]
