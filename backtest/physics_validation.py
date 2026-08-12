# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics-based validation for backtesting.

Integrates physics conservation laws into backtest validation to ensure:
- Realistic energy and momentum conservation
- Detection of unrealistic strategy assumptions
- Physical stability guarantees
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.physics.conservation import (
    check_proxy_drift,
    compute_flow_momentum_proxy,
    compute_volatility_energy_proxy,
)


@dataclass
class PhysicsBacktestMetrics:
    """Physics-based metrics for backtest validation.

    Tracks conservation violations and physical consistency throughout
    the backtest.

    Attributes:
        energy_violations: Count of energy conservation violations
        momentum_violations: Count of momentum conservation violations
        max_energy_violation: Maximum energy violation magnitude
        max_momentum_violation: Maximum momentum violation magnitude
        total_timesteps: Total timesteps in backtest
        violation_timestamps: Timestamps where violations occurred
    """

    energy_violations: int = 0
    momentum_violations: int = 0
    max_energy_violation: float = 0.0
    max_momentum_violation: float = 0.0
    total_timesteps: int = 0
    violation_timestamps: list[int] = field(default_factory=list)

    @property
    def energy_violation_rate(self) -> float:
        """Fraction of timesteps with energy violations."""
        if self.total_timesteps == 0:
            return 0.0
        return self.energy_violations / self.total_timesteps

    @property
    def momentum_violation_rate(self) -> float:
        """Fraction of timesteps with momentum violations."""
        if self.total_timesteps == 0:
            return 0.0
        return self.momentum_violations / self.total_timesteps

    @property
    def overall_violation_rate(self) -> float:
        """Fraction of timesteps with any violation."""
        if self.total_timesteps == 0:
            return 0.0
        return len(self.violation_timestamps) / self.total_timesteps


class PhysicsBacktestValidator:
    """Validator for physics-based backtest checks.

    Monitors energy and momentum conservation throughout backtesting to
    detect unrealistic strategy behavior.

    Attributes:
        energy_tolerance: Tolerance for energy conservation (default: 10%)
        momentum_tolerance: Tolerance for momentum conservation (default: 10%)
        metrics: Accumulated physics metrics

    Example:
        >>> validator = PhysicsBacktestValidator()
        >>>
        >>> # During backtest loop
        >>> for t in range(len(data) - 1):
        ...     validator.check_timestep(
        ...         timestep=t,
        ...         prices_before=data[t]["prices"],
        ...         prices_after=data[t+1]["prices"],
        ...         volumes_before=data[t]["volumes"],
        ...         volumes_after=data[t+1]["volumes"]
        ...     )
        >>>
        >>> # After backtest
        >>> metrics = validator.get_metrics()
        >>> if metrics.energy_violation_rate > 0.1:
        ...     print("Warning: High energy violation rate!")
        >>>
        >>> report = validator.generate_report()
        >>> print(report)
    """

    def __init__(
        self,
        *,
        energy_tolerance: float = 0.1,
        momentum_tolerance: float = 0.1,
    ) -> None:
        """Initialize physics validator for backtesting.

        Args:
            energy_tolerance: Relative tolerance for energy conservation
            momentum_tolerance: Relative tolerance for momentum conservation
        """
        self.energy_tolerance = float(energy_tolerance)
        self.momentum_tolerance = float(momentum_tolerance)
        self.metrics = PhysicsBacktestMetrics()

    def check_timestep(
        self,
        timestep: int,
        prices_before: np.ndarray | list[float],
        prices_after: np.ndarray | list[float],
        volumes_before: np.ndarray | list[float] | None = None,
        volumes_after: np.ndarray | list[float] | None = None,
    ) -> dict[str, Any]:
        """Check physics conservation for a single timestep.

        Args:
            timestep: Current timestep index
            prices_before: Price array at time t
            prices_after: Price array at time t+1
            volumes_before: Optional volume array at time t
            volumes_after: Optional volume array at time t+1

        Returns:
            Dictionary with violation info for this timestep
        """
        prices1 = np.asarray(prices_before, dtype=float)
        prices2 = np.asarray(prices_after, dtype=float)

        vols1 = np.asarray(volumes_before, dtype=float) if volumes_before is not None else None
        vols2 = np.asarray(volumes_after, dtype=float) if volumes_after is not None else None

        # Compute energies
        # Volatility-energy proxy (NOT physical energy — see
        # core/physics/conservation.py module docstring; audit 2026-04-30).
        energy1 = compute_volatility_energy_proxy(prices1, vols1)
        energy2 = compute_volatility_energy_proxy(prices2, vols2)

        # Drift check (NOT a conservation law).
        energy_conserved, energy_violation = check_proxy_drift(
            energy1, energy2, tolerance=self.energy_tolerance
        )

        # Flow-momentum proxy (NOT physical momentum).
        momentum1 = compute_flow_momentum_proxy(prices1, vols1)
        momentum2 = compute_flow_momentum_proxy(prices2, vols2)

        # Drift check (NOT a conservation law).
        momentum_conserved, momentum_violation = check_proxy_drift(
            momentum1, momentum2, tolerance=self.momentum_tolerance
        )

        # Update metrics
        self.metrics.total_timesteps += 1

        has_violation = False
        if not energy_conserved:
            self.metrics.energy_violations += 1
            self.metrics.max_energy_violation = max(
                self.metrics.max_energy_violation, energy_violation
            )
            has_violation = True

        if not momentum_conserved:
            self.metrics.momentum_violations += 1
            self.metrics.max_momentum_violation = max(
                self.metrics.max_momentum_violation, momentum_violation
            )
            has_violation = True

        if has_violation:
            self.metrics.violation_timestamps.append(timestep)

        return {
            "timestep": timestep,
            "energy_conserved": energy_conserved,
            "momentum_conserved": momentum_conserved,
            "energy_violation": energy_violation,
            "momentum_violation": momentum_violation,
            "energy_before": energy1,
            "energy_after": energy2,
            "momentum_before": momentum1,
            "momentum_after": momentum2,
        }

    def get_metrics(self) -> PhysicsBacktestMetrics:
        """Get accumulated physics metrics.

        Returns:
            PhysicsBacktestMetrics with violation statistics
        """
        return self.metrics

    def reset(self) -> None:
        """Reset metrics for new backtest."""
        self.metrics = PhysicsBacktestMetrics()

    def generate_report(self) -> str:
        """Generate human-readable report of physics validation.

        Returns:
            Formatted string report
        """
        m = self.metrics

        lines = [
            "=" * 60,
            "Physics-Based Backtest Validation Report",
            "=" * 60,
            "",
            f"Total Timesteps: {m.total_timesteps}",
            "",
            "Energy Conservation:",
            f"  Violations: {m.energy_violations} ({m.energy_violation_rate:.1%})",
            f"  Max Violation: {m.max_energy_violation:.2%}",
            f"  Tolerance: {self.energy_tolerance:.1%}",
            "",
            "Momentum Conservation:",
            f"  Violations: {m.momentum_violations} ({m.momentum_violation_rate:.1%})",
            f"  Max Violation: {m.max_momentum_violation:.2%}",
            f"  Tolerance: {self.momentum_tolerance:.1%}",
            "",
            f"Overall Violation Rate: {m.overall_violation_rate:.1%}",
            "",
        ]

        # Add recommendations
        if m.overall_violation_rate > 0.2:
            lines.extend(
                [
                    "⚠️  WARNING: High violation rate (>20%)",
                    "   - Strategy may be exploiting unrealistic assumptions",
                    "   - Consider reviewing order execution model",
                    "   - Check for look-ahead bias or data leakage",
                    "",
                ]
            )
        elif m.overall_violation_rate > 0.1:
            lines.extend(
                [
                    "⚠️  CAUTION: Moderate violation rate (>10%)",
                    "   - Review violations at specific timestamps",
                    "   - May indicate regime changes or external events",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "✓  Physics validation passed",
                    "   - Low violation rate indicates realistic behavior",
                    "",
                ]
            )

        lines.append("=" * 60)

        return "\n".join(lines)


__all__ = [
    "PhysicsBacktestMetrics",
    "PhysicsBacktestValidator",
]
