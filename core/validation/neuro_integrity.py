"""Neural pathway integrity validation for neuroscience-inspired trading components.

This module provides validators that ensure coherence and integrity of neural
pathway signals in the neuroscience-inspired trading system. The neuro foundation
ensures that signal processing maintains biological plausibility and stability.

Key Components:
    PathwayState: Snapshot of neural pathway activation and coherence
    NeuroIntegrityConfig: Configuration for acceptable neural signal ranges
    NeuroIntegrityReport: Validation results with pathway diagnostics
    NeuroIntegrity: Main validator enforcing neural coherence

The validator implements:
    - Activation bounds: Signals within biologically plausible ranges
    - Coherence validation: Phase synchrony and correlation constraints
    - Homeostatic balance: Excitation/inhibition equilibrium
    - Temporal consistency: Rate-of-change limits for neural signals

Example:
    >>> config = NeuroIntegrityConfig()
    >>> validator = NeuroIntegrity(config)
    >>> state = PathwayState(
    ...     dopamine=0.5, serotonin=0.4, excitation=0.6, inhibition=0.4
    ... )
    >>> report = validator.validate_state(state)
    >>> print(f"Valid: {report.is_valid}, Balance: {report.ei_balance:.2f}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np


@dataclass(frozen=True, slots=True)
class PathwayState:
    """Snapshot of neural pathway activation levels.

    All values are normalized to [0, 1] range representing relative
    activation from baseline to maximum firing rate.

    Attributes:
        dopamine: Dopamine pathway activation (reward/motivation signal)
        serotonin: Serotonin pathway activation (risk inhibition signal)
        excitation: Global excitatory drive
        inhibition: Global inhibitory drive
        norepinephrine: Norepinephrine level (arousal/attention)
        acetylcholine: Acetylcholine level (learning modulation)
        gaba: GABA inhibitory tone
        glutamate: Glutamate excitatory tone
        coherence: Phase coherence across pathways (0=desync, 1=sync)
        timestamp_ms: Optional timestamp in milliseconds
    """

    dopamine: float
    serotonin: float
    excitation: float
    inhibition: float
    norepinephrine: float = 0.5
    acetylcholine: float = 0.5
    gaba: float = 0.5
    glutamate: float = 0.5
    coherence: float = 0.5
    timestamp_ms: float | None = None

    def __post_init__(self) -> None:
        """Validate that all activation values are in [0, 1]."""
        for attr in (
            "dopamine",
            "serotonin",
            "excitation",
            "inhibition",
            "norepinephrine",
            "acetylcholine",
            "gaba",
            "glutamate",
            "coherence",
        ):
            value = getattr(self, attr)
            if not np.isfinite(value):
                raise ValueError(f"{attr} must be finite, got {value}")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{attr} must be in [0, 1], got {value}")

    @property
    def ei_balance(self) -> float:
        """Calculate excitation-inhibition balance ratio.

        Returns:
            Ratio > 1 indicates excitation dominance,
            < 1 indicates inhibition dominance,
            = 1 indicates perfect balance.
        """
        if self.inhibition < 1e-10:
            return float("inf") if self.excitation > 0 else 1.0
        return self.excitation / self.inhibition

    @property
    def neuromodulator_balance(self) -> float:
        """Calculate dopamine-serotonin balance (reward vs. risk signal)."""
        total = self.dopamine + self.serotonin
        if total < 1e-10:
            return 0.5  # Neutral
        return self.dopamine / total

    def as_mapping(self) -> Mapping[str, float]:
        """Return state as a dictionary for serialization."""
        return {
            "dopamine": self.dopamine,
            "serotonin": self.serotonin,
            "excitation": self.excitation,
            "inhibition": self.inhibition,
            "norepinephrine": self.norepinephrine,
            "acetylcholine": self.acetylcholine,
            "gaba": self.gaba,
            "glutamate": self.glutamate,
            "coherence": self.coherence,
            "ei_balance": self.ei_balance,
            "neuromodulator_balance": self.neuromodulator_balance,
        }


@dataclass(frozen=True, slots=True)
class NeuroIntegrityConfig:
    """Configuration for neural pathway integrity validation.

    Attributes:
        min_coherence: Minimum acceptable phase coherence
        max_ei_imbalance: Maximum excitation/inhibition ratio deviation from 1.0
        max_activation_rate: Maximum change in activation per second
        min_total_activation: Minimum sum of all pathway activations
        max_total_activation: Maximum sum of all pathway activations
        dopamine_serotonin_correlation_min: Minimum inverse correlation expectation
        homeostatic_tolerance: Tolerance for homeostatic balance checks
    """

    min_coherence: float = 0.1
    max_ei_imbalance: float = 5.0  # E/I ratio should be in [0.2, 5.0]
    max_activation_rate: float = 2.0  # Max change per second
    min_total_activation: float = 0.1  # Prevent total neural silence
    max_total_activation: float = 7.0  # Prevent runaway activation
    dopamine_serotonin_correlation_min: float = -0.8  # Expected inverse correlation
    homeostatic_tolerance: float = 0.3


@dataclass(slots=True)
class NeuroIntegrityReport:
    """Detailed report of neural integrity validation.

    Attributes:
        is_valid: True if all constraints satisfied
        ei_balance: Excitation/inhibition ratio
        coherence: Phase coherence value
        total_activation: Sum of pathway activations
        violations: List of violated constraint descriptions
        warnings: List of near-violation warnings
        metrics: Additional diagnostic metrics
    """

    is_valid: bool
    ei_balance: float
    coherence: float
    total_activation: float
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


class NeuroIntegrity:
    """Validator enforcing neural pathway coherence and integrity.

    The validator checks that neural pathway states maintain:

    1. Activation Bounds: All signals in biologically plausible ranges
    2. E/I Balance: Excitation-inhibition ratio within stable bounds
    3. Coherence: Minimum phase synchrony across pathways
    4. Homeostasis: Total activation within viable range
    5. Rate Limits: Signal changes within physiological limits

    Example:
        >>> validator = NeuroIntegrity()
        >>> state = PathwayState(dopamine=0.6, serotonin=0.3, excitation=0.5, inhibition=0.5)
        >>> report = validator.validate_state(state)
        >>> assert report.is_valid
    """

    def __init__(self, config: NeuroIntegrityConfig | None = None) -> None:
        """Initialize validator with configuration.

        Args:
            config: Neural integrity configuration. Uses defaults if None.
        """
        self.config = config or NeuroIntegrityConfig()

    def validate_state(self, state: PathwayState) -> NeuroIntegrityReport:
        """Validate a single neural pathway state.

        Args:
            state: The pathway state to validate.

        Returns:
            NeuroIntegrityReport with validation results.
        """
        total_activation = (
            state.dopamine
            + state.serotonin
            + state.excitation
            + state.inhibition
            + state.norepinephrine
            + state.acetylcholine
            + state.gaba
            + state.glutamate
        )

        report = NeuroIntegrityReport(
            is_valid=True,
            ei_balance=state.ei_balance,
            coherence=state.coherence,
            total_activation=total_activation,
        )

        # Check coherence
        if state.coherence < self.config.min_coherence:
            report.add_violation(
                f"Coherence {state.coherence:.3f} below minimum {self.config.min_coherence:.3f}"
            )
        elif state.coherence < 2 * self.config.min_coherence:
            report.add_warning(f"Low coherence: {state.coherence:.3f}")

        # Check E/I balance
        ei = state.ei_balance
        if ei > self.config.max_ei_imbalance:
            report.add_violation(
                f"E/I ratio {ei:.2f} exceeds maximum {self.config.max_ei_imbalance:.2f} "
                "(excitation dominant)"
            )
        elif ei < 1.0 / self.config.max_ei_imbalance:
            report.add_violation(
                f"E/I ratio {ei:.2f} below minimum {1.0 / self.config.max_ei_imbalance:.2f} "
                "(inhibition dominant)"
            )

        # Check total activation bounds
        if total_activation < self.config.min_total_activation:
            report.add_violation(
                f"Total activation {total_activation:.2f} below minimum "
                f"{self.config.min_total_activation:.2f} (neural silence)"
            )
        elif total_activation > self.config.max_total_activation:
            report.add_violation(
                f"Total activation {total_activation:.2f} exceeds maximum "
                f"{self.config.max_total_activation:.2f} (runaway activation)"
            )

        # Check homeostatic balance (GABA vs glutamate)
        gaba_glut_ratio = state.gaba / max(state.glutamate, 1e-10)
        if abs(gaba_glut_ratio - 1.0) > self.config.homeostatic_tolerance * 5:
            report.add_warning(f"GABA/Glutamate imbalance: ratio={gaba_glut_ratio:.2f}")

        # Populate metrics
        report.metrics.update(state.as_mapping())
        report.metrics["total_activation"] = total_activation
        report.metrics["gaba_glutamate_ratio"] = gaba_glut_ratio

        return report

    def validate_transition(
        self,
        state_before: PathwayState,
        state_after: PathwayState,
        dt: float,
    ) -> NeuroIntegrityReport:
        """Validate a neural state transition.

        Args:
            state_before: Initial pathway state.
            state_after: Final pathway state.
            dt: Time delta in seconds (must be positive).

        Returns:
            NeuroIntegrityReport with validation results.

        Raises:
            ValueError: If dt is not positive.
        """
        if dt <= 0:
            raise ValueError(f"Time delta must be positive, got {dt}")

        # Validate both states
        before_report = self.validate_state(state_before)
        after_report = self.validate_state(state_after)

        report = NeuroIntegrityReport(
            is_valid=True,
            ei_balance=state_after.ei_balance,
            coherence=state_after.coherence,
            total_activation=after_report.total_activation,
        )

        for violation in before_report.violations:
            report.add_violation(f"Initial: {violation}")
        for violation in after_report.violations:
            report.add_violation(f"Final: {violation}")

        # Check activation rate limits
        max_rate = self.config.max_activation_rate
        for attr in ("dopamine", "serotonin", "excitation", "inhibition"):
            before_val = getattr(state_before, attr)
            after_val = getattr(state_after, attr)
            rate = abs(after_val - before_val) / dt
            if rate > max_rate:
                report.add_violation(
                    f"{attr} change rate {rate:.2f}/s exceeds maximum {max_rate:.2f}/s"
                )

        # Check coherence stability
        coherence_change = abs(state_after.coherence - state_before.coherence)
        if coherence_change > 0.5:  # Large coherence swing
            report.add_warning(
                f"Large coherence change: {state_before.coherence:.2f} -> "
                f"{state_after.coherence:.2f}"
            )

        # Populate transition metrics
        report.metrics.update(
            {
                "dt": dt,
                "dopamine_delta": state_after.dopamine - state_before.dopamine,
                "serotonin_delta": state_after.serotonin - state_before.serotonin,
                "excitation_delta": state_after.excitation - state_before.excitation,
                "inhibition_delta": state_after.inhibition - state_before.inhibition,
                "coherence_delta": state_after.coherence - state_before.coherence,
            }
        )

        return report

    def validate_trajectory(
        self,
        states: list[PathwayState],
        timestamps_ms: list[float] | None = None,
    ) -> NeuroIntegrityReport:
        """Validate a sequence of neural pathway states.

        Args:
            states: List of sequential pathway states.
            timestamps_ms: Optional list of timestamps in milliseconds.

        Returns:
            Aggregate NeuroIntegrityReport for the trajectory.
        """
        if len(states) < 1:
            return NeuroIntegrityReport(
                is_valid=True,
                ei_balance=1.0,
                coherence=0.5,
                total_activation=0.0,
            )

        if len(states) == 1:
            return self.validate_state(states[0])

        # Compute trajectory statistics
        coherences = [s.coherence for s in states]
        ei_balances = [s.ei_balance for s in states]

        report = NeuroIntegrityReport(
            is_valid=True,
            ei_balance=float(np.mean([b for b in ei_balances if np.isfinite(b)])),
            coherence=float(np.mean(coherences)),
            total_activation=0.0,
        )

        # Validate each transition
        for i in range(1, len(states)):
            if timestamps_ms is not None:
                dt = (timestamps_ms[i] - timestamps_ms[i - 1]) / 1000.0
            elif (
                states[i].timestamp_ms is not None
                and states[i - 1].timestamp_ms is not None
            ):
                dt = (states[i].timestamp_ms - states[i - 1].timestamp_ms) / 1000.0
            else:
                dt = 1.0

            if dt <= 0:
                continue

            step_report = self.validate_transition(states[i - 1], states[i], dt)
            for violation in step_report.violations:
                report.add_violation(f"Step {i}: {violation}")
            for warning in step_report.warnings:
                report.add_warning(f"Step {i}: {warning}")

        # Trajectory-level metrics
        report.metrics["trajectory_length"] = len(states)
        report.metrics["mean_coherence"] = float(np.mean(coherences))
        report.metrics["std_coherence"] = float(np.std(coherences))
        report.metrics["min_coherence"] = float(np.min(coherences))
        report.metrics["max_coherence"] = float(np.max(coherences))

        return report


def compute_pathway_correlation(
    dopamine_series: np.ndarray,
    serotonin_series: np.ndarray,
) -> float:
    """Compute correlation between dopamine and serotonin pathways.

    In healthy neural systems, these pathways often show inverse correlation
    (reward seeking vs. risk aversion).

    Args:
        dopamine_series: Time series of dopamine activation.
        serotonin_series: Time series of serotonin activation.

    Returns:
        Pearson correlation coefficient in [-1, 1].
    """
    if len(dopamine_series) != len(serotonin_series):
        raise ValueError("Series must have equal length")
    if len(dopamine_series) < 2:
        return 0.0

    dopamine = np.asarray(dopamine_series, dtype=float)
    serotonin = np.asarray(serotonin_series, dtype=float)

    # Handle constant series
    if np.std(dopamine) < 1e-10 or np.std(serotonin) < 1e-10:
        return 0.0

    correlation = np.corrcoef(dopamine, serotonin)[0, 1]
    return float(correlation) if np.isfinite(correlation) else 0.0


def compute_phase_coherence(phases: np.ndarray) -> float:
    """Compute phase coherence across neural oscillators.

    Uses Kuramoto-style order parameter to measure synchrony.

    Args:
        phases: Array of phase angles in radians.

    Returns:
        Coherence value in [0, 1] where 1 = perfect synchrony.
    """
    if len(phases) == 0:
        return 0.0

    phases = np.asarray(phases, dtype=float)
    phases = phases[np.isfinite(phases)]

    if len(phases) == 0:
        return 0.0

    # Kuramoto order parameter
    complex_order = np.mean(np.exp(1j * phases))
    return float(np.abs(complex_order))


__all__ = [
    "PathwayState",
    "NeuroIntegrityConfig",
    "NeuroIntegrityReport",
    "NeuroIntegrity",
    "compute_pathway_correlation",
    "compute_phase_coherence",
]
