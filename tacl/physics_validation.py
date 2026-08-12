# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Enhanced TACL validation with physics-based conservation checks.

Extends the existing TACL energy validation with additional physics principles:
- Conservation law verification
- Momentum tracking
- Physical stability guarantees
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tacl.energy_model import EnergyMetrics, EnergyValidationResult, EnergyValidator

from ..physics.conservation import (
    check_proxy_drift,
    compute_flow_momentum_proxy,
    compute_volatility_energy_proxy,
)


@dataclass(frozen=True, slots=True)
class PhysicsValidationResult:
    """Results from physics-based validation checks."""

    energy_conserved: bool
    momentum_conserved: bool
    energy_violation: float
    momentum_violation: float
    total_energy: float
    total_momentum: float
    reason: str | None = None


class PhysicsEnhancedValidator:
    """Enhanced validator combining TACL with physics conservation laws.

    This validator extends the existing TACL thermodynamic validation with
    additional checks from conservation laws, providing stronger guarantees
    about system behavior.

    Attributes:
        base_validator: Underlying TACL energy validator
        energy_tolerance: Tolerance for energy conservation (default: 5%)
        momentum_tolerance: Tolerance for momentum conservation (default: 5%)

    Example:
        >>> validator = PhysicsEnhancedValidator()
        >>> # Check TACL metrics
        >>> tacl_result = validator.validate_tacl(metrics)
        >>> # Check physics conservation
        >>> physics_result = validator.validate_physics(
        ...     prices_before, prices_after, volumes
        ... )
        >>> if not physics_result.energy_conserved:
        ...     print("Warning: Energy conservation violated!")
    """

    def __init__(
        self,
        *,
        energy_tolerance: float = 0.05,
        momentum_tolerance: float = 0.05,
        tacl_validator: EnergyValidator | None = None,
    ) -> None:
        """Initialize enhanced validator.

        Args:
            energy_tolerance: Relative tolerance for energy conservation
            momentum_tolerance: Relative tolerance for momentum conservation
            tacl_validator: Optional existing TACL validator to use
        """
        self.base_validator = tacl_validator or EnergyValidator()
        self.energy_tolerance = float(energy_tolerance)
        self.momentum_tolerance = float(momentum_tolerance)

    def validate_tacl(self, metrics: EnergyMetrics) -> EnergyValidationResult:
        """Validate using existing TACL thermodynamic checks.

        Args:
            metrics: TACL energy metrics

        Returns:
            EnergyValidationResult from TACL validator
        """
        return self.base_validator.validate(metrics)

    def validate_physics(
        self,
        prices_before: Iterable[float],
        prices_after: Iterable[float],
        volumes_before: Iterable[float] | None = None,
        volumes_after: Iterable[float] | None = None,
    ) -> PhysicsValidationResult:
        """Validate using physics conservation laws.

        Checks both energy and momentum conservation between two states.
        Violations indicate external forces or regime changes.

        Args:
            prices_before: Price array at time t
            prices_after: Price array at time t+1
            volumes_before: Optional volume array at time t
            volumes_after: Optional volume array at time t+1

        Returns:
            PhysicsValidationResult with conservation status
        """
        import numpy as np

        prices1 = np.asarray(list(prices_before), dtype=float)
        prices2 = np.asarray(list(prices_after), dtype=float)

        vols1 = (
            np.asarray(list(volumes_before), dtype=float) if volumes_before is not None else None
        )
        vols2 = np.asarray(list(volumes_after), dtype=float) if volumes_after is not None else None

        # Compute energies
        energy1 = compute_volatility_energy_proxy(prices1, vols1)
        energy2 = compute_volatility_energy_proxy(prices2, vols2)

        # Check energy conservation
        energy_conserved, energy_violation = check_proxy_drift(
            energy1, energy2, tolerance=self.energy_tolerance
        )

        # Compute momenta
        momentum1 = compute_flow_momentum_proxy(prices1, vols1)
        momentum2 = compute_flow_momentum_proxy(prices2, vols2)

        # Check momentum conservation
        momentum_conserved, momentum_violation = check_proxy_drift(
            momentum1, momentum2, tolerance=self.momentum_tolerance
        )

        # Build reason if violations detected
        reason = None
        if not energy_conserved or not momentum_conserved:
            parts = []
            if not energy_conserved:
                parts.append(f"Energy violation: {energy_violation:.2%}")
            if not momentum_conserved:
                parts.append(f"Momentum violation: {momentum_violation:.2%}")
            reason = "; ".join(parts)

        return PhysicsValidationResult(
            energy_conserved=energy_conserved,
            momentum_conserved=momentum_conserved,
            energy_violation=energy_violation,
            momentum_violation=momentum_violation,
            total_energy=energy2,
            total_momentum=momentum2,
            reason=reason,
        )

    def validate_combined(
        self,
        tacl_metrics: EnergyMetrics,
        prices_before: Iterable[float],
        prices_after: Iterable[float],
        volumes_before: Iterable[float] | None = None,
        volumes_after: Iterable[float] | None = None,
    ) -> tuple[EnergyValidationResult, PhysicsValidationResult]:
        """Perform both TACL and physics validation.

        Args:
            tacl_metrics: TACL energy metrics
            prices_before: Price array at time t
            prices_after: Price array at time t+1
            volumes_before: Optional volume array at time t
            volumes_after: Optional volume array at time t+1

        Returns:
            Tuple of (TACL result, Physics result)
        """
        tacl_result = self.validate_tacl(tacl_metrics)
        physics_result = self.validate_physics(
            prices_before, prices_after, volumes_before, volumes_after
        )

        return tacl_result, physics_result


class PhysicsValidationError(RuntimeError):
    """Raised when physics validation fails."""

    def __init__(self, message: str, result: PhysicsValidationResult) -> None:
        super().__init__(message)
        self.result = result


__all__ = [
    "PhysicsValidationResult",
    "PhysicsEnhancedValidator",
    "PhysicsValidationError",
]
