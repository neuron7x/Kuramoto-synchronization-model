# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T3 — Portfolio Energy-Budget Tolerance Check.

Provenance tier: EXTRAPOLATED (heuristic, not an anchored physical law).

Defines a descriptive scalar "energy" for a portfolio configuration:
    E_kinetic   = ½ · Σ(|position_i| · return_i²)
        where return_i = 5-period price return (a velocity proxy)
    E_potential = -Σ(position_i · expected_return_i)
        where expected_return comes from a Kuramoto coherence signal
    E_total     = E_kinetic + E_potential

Budget-tolerance check (NOT a conservation law):
    |ΔE_total| per rebalance ≤ ε  (ε is a tunable threshold, default 0.05)

What this is NOT
----------------
This is NOT a Noether conservation law. There is no continuous symmetry
of the portfolio dynamics and no associated conserved current, so nothing
is "conserved" in the physical sense and the rebalance does not "preserve"
any quantity. E_total is a hand-assembled descriptive scalar, not a
Hamiltonian; the negative sign on E_potential is a heuristic stability
ranking (aligned positions score lower), not a gravitational potential.

What this IS
------------
A budget tolerance: |ΔE| ≤ ε flags rebalances whose descriptive-energy
change exceeds the band ε. ε is a free, tunable threshold (it requires
calibration via transaction-cost analysis); it is NOT a derived physical
constant, and the comparison verdict carries no conservation-law authority.

A flagged move (|ΔE| > ε) is read as a large/regime-driven reconfiguration
relative to the chosen budget, not as a violation of any law of physics.
"""

from __future__ import annotations

import logging

import numpy as np
from numpy.typing import NDArray

_logger = logging.getLogger(__name__)


class PortfolioEnergyConservation:
    """Energy-budget tolerance check for portfolio rebalances.

    EXTRAPOLATED heuristic, NOT a Noether conservation law: there is no
    continuous symmetry and no associated current. The class name and the
    ``check_conservation`` method name are retained only for API/consumer
    stability; the underlying semantics are a tolerance band ``|ΔE| ≤ ε``
    on a descriptive scalar, not a preserved physical quantity.

    Parameters
    ----------
    epsilon : float
        Budget tolerance: maximum allowed |ΔE| per rebalance (default 0.05).
        Tunable threshold — NOT a derived physical constant; requires
        calibration via transaction-cost analysis.
    return_window : int
        Window for computing price returns as a velocity proxy (default 5).
    """

    def __init__(self, epsilon: float = 0.05, return_window: int = 5) -> None:
        if epsilon < 0:
            raise ValueError(f"epsilon must be ≥ 0, got {epsilon}")
        if return_window < 1:
            raise ValueError(f"return_window must be ≥ 1, got {return_window}")
        self._epsilon = epsilon
        self._return_window = return_window
        self._violation_count = 0

    @property
    def epsilon(self) -> float:
        return self._epsilon

    @property
    def violation_count(self) -> int:
        return self._violation_count

    @staticmethod
    def compute_kinetic(
        positions: NDArray[np.float64],
        returns: NDArray[np.float64],
    ) -> float:
        """E_kinetic = ½ · Σ(|position_i| · return_i²).

        Uses |position| to ensure kinetic energy is non-negative.
        """
        positions = np.asarray(positions, dtype=np.float64)
        returns = np.asarray(returns, dtype=np.float64)
        if positions.shape != returns.shape:
            raise ValueError(
                f"positions and returns must match: {positions.shape} vs {returns.shape}"
            )
        return 0.5 * float(np.sum(np.abs(positions) * returns**2))

    @staticmethod
    def compute_potential(
        positions: NDArray[np.float64],
        expected_returns: NDArray[np.float64],
    ) -> float:
        """E_potential = -Σ(position_i · expected_return_i).

        Negative sign is a heuristic stability ranking: positions aligned with
        expected returns score lower ("more stable"). This is a descriptive
        scoring convention, NOT a physical potential and NOT a gravitational
        potential — there is no field, no force, and no conserved energy here.
        """
        positions = np.asarray(positions, dtype=np.float64)
        expected_returns = np.asarray(expected_returns, dtype=np.float64)
        if positions.shape != expected_returns.shape:
            raise ValueError(
                f"positions and expected_returns must match: "
                f"{positions.shape} vs {expected_returns.shape}"
            )
        return -float(np.sum(positions * expected_returns))

    def compute_total(
        self,
        positions: NDArray[np.float64],
        returns: NDArray[np.float64],
        expected_returns: NDArray[np.float64],
    ) -> float:
        """E_total = E_kinetic + E_potential."""
        ek = self.compute_kinetic(positions, returns)
        ep = self.compute_potential(positions, expected_returns)
        return ek + ep

    def check_conservation(
        self,
        E_before: float,
        E_after: float,
    ) -> bool:
        """Check the budget tolerance |ΔE| ≤ ε (NOT a conservation law).

        Returns True when the descriptive-energy change is within the tunable
        budget ε. If |ΔE| exceeds ε, increments an internal counter and logs a
        warning — this flags a large/regime-driven reconfiguration relative to
        the chosen budget, not a violated physical law. Method name kept for
        consumer/API stability.
        """
        delta = abs(E_after - E_before)
        # |ΔE| ≤ ε budget tolerance (byte-identical comparison; ε is a tunable
        # threshold, not a derived constant). Within-band → no flag.
        conserved = delta <= self._epsilon
        if not conserved:
            self._violation_count += 1
            _logger.warning(
                "Energy budget tolerance exceeded: ΔE=%.6f > ε=%.6f (flag #%d)",
                delta,
                self._epsilon,
                self._violation_count,
            )
        return conserved

    def reset_violations(self) -> None:
        """Reset the budget-tolerance flag counter."""
        self._violation_count = 0


__all__ = ["PortfolioEnergyConservation"]
