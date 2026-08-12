# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T4 — Free-energy-analog risk gate (Lyapunov control objective).

PROVENANCE TIER: EXTRAPOLATED (control heuristic, NOT an anchored law).
This module borrows the *form* of Helmholtz free energy as a control
Lyapunov candidate. It is not a derivation of a physical law and must not
be cited as one. See the "What this is NOT" note below.

Shannon entropy:
    S = -Σ w_i · log(w_i)   where w_i = |pos_i| / Σ|pos_j|

Tsallis entropy (q-generalisation for fat tails):
    S_q = (1 - Σ w_i^q) / (q-1),  q=1.5

    q=1.5 justification: empirically fitted to Pareto-distributed
    financial returns (Borland 2002, Tsallis et al. 2003). The
    q-Gaussian with q≈1.5 reproduces heavy tails observed in
    intraday returns. This is a calibrated parameter, not intuition.

Ricci curvature coupling:
    T_effective = T_base · exp(-κ_min)
    Negative curvature → higher T → more entropy allowed → looser gate.
    Positive curvature → lower T → tighter gate → more conservative.

Free-energy-analog gate (control objective, not a law):
    F = U - T_eff · S_q
    The gate ADMITS a position update iff dF ≤ 0. F is a control Lyapunov
    *candidate* that the controller actively drives down by rejecting
    updates with dF > 0 — it is NOT a quantity nature conserves or
    monotonically increases. dS may be of either sign and the gate is
    designed to handle both:
        dS > 0 (diversification) → −T·dS lowers F → easier to admit.
        dS < 0 (concentration)   → −T·dS raises F → penalised, harder to
                                    admit. This is the gate's job.

What this is NOT:
    * NOT a second law. "dS ≥ 0" does NOT hold for portfolio weight
      entropy: a rebalance toward concentration gives dS < 0 (see
      shannon_entropy on a concentrated vs uniform book). The previous
      docstring asserted a "second-law analog (diversification increases
      entropy)" — that is false for this quantity and is removed. The
      gate never relied on dS ≥ 0; it accepts arbitrary-sign dS as a free
      input and the −T·dS term supplies the penalty.
    * NOT dimensionally a physical free energy. T_eff is a dimensionless
      control temperature, S is in nats, dU is a P&L/return delta; there
      is no k_B and no energy scale. F is a unitless control potential.
      Treat the units as nondimensional control quantities, not joules.

T_base=0.60: derived from TACL calibration in tacl/energy_model.py,
not from intuition. The value matches the production temperature used
in the EnergyModel class.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class ThermodynamicRiskGate:
    """Thermodynamic risk gate using Tsallis entropy and Ricci curvature.

    Parameters
    ----------
    q : float
        Tsallis entropic index (default 1.5).
    T_base : float
        Base temperature from TACL calibration (default 0.60).
    """

    def __init__(self, q: float = 1.5, T_base: float = 0.60) -> None:
        if q <= 0:
            raise ValueError(f"q must be > 0, got {q}")
        if abs(q - 1.0) < 1e-12:
            raise ValueError("q=1.0 degenerates; use shannon_entropy instead")
        if T_base <= 0:
            raise ValueError(f"T_base must be > 0, got {T_base}")
        self._q = q
        self._T_base = T_base

    @property
    def q(self) -> float:
        return self._q

    @property
    def T_base(self) -> float:
        return self._T_base

    @staticmethod
    def shannon_entropy(weights: NDArray[np.float64]) -> float:
        """S = -Σ w_i · ln(w_i) for position weight distribution.

        Input weights are normalised internally: w_i = |pos_i| / Σ|pos_j|.
        """
        w = np.asarray(weights, dtype=np.float64)
        w = np.abs(w)
        total = w.sum()
        if total < 1e-12:
            return 0.0
        w = w / total
        nonzero = w[w > 0]
        return -float(np.sum(nonzero * np.log(nonzero)))

    def tsallis_entropy(self, weights: NDArray[np.float64]) -> float:
        """S_q = (1 - Σ w_i^q) / (q-1).

        q=1.5 captures fat-tailed portfolio weight distributions.
        As q→1, reduces to Shannon entropy (L'Hôpital).
        """
        w = np.asarray(weights, dtype=np.float64)
        w = np.abs(w)
        total = w.sum()
        if total < 1e-12:
            return 0.0
        w = w / total
        return (1.0 - float(np.sum(w**self._q))) / (self._q - 1.0)

    def ricci_temperature(self, kappa_min: float) -> float:
        """T_eff = T_base · exp(-κ_min).

        κ_min < 0 (negative curvature) → T_eff > T_base → looser risk.
        κ_min > 0 (positive curvature) → T_eff < T_base → tighter risk.
        """
        return float(self._T_base * np.exp(-kappa_min))

    @staticmethod
    def free_energy(U: float, T: float, S: float) -> float:
        """F = U - T·S (Helmholtz-analog control potential, dimensionless).

        Not a physical free energy: T is a dimensionless control
        temperature, S is in nats, no k_B. Used only as a Lyapunov
        candidate the gate drives down.
        """
        return U - T * S

    def gate(self, dU: float, dS: float, kappa_min: float = 0.0) -> bool:
        """Free energy gate with Ricci-coupled temperature.

        Parameters
        ----------
        dU : float
            Change in internal energy (P&L delta).
        dS : float
            Change in Tsallis entropy.
        kappa_min : float
            Minimum Ollivier-Ricci curvature from network.

        Returns
        -------
        True if dF ≤ 0 (position update admitted). dS may be of either
        sign: concentration (dS < 0) is penalised via −T·dS, not assumed
        away. The gate enforces the control objective; it does not assert
        a second law.
        """
        T_eff = self.ricci_temperature(kappa_min)
        dF = dU - T_eff * dS
        return dF <= 0.0

    def gate_with_details(
        self, dU: float, dS: float, kappa_min: float = 0.0
    ) -> dict[str, float | bool]:
        """Gate with full diagnostic output."""
        T_eff = self.ricci_temperature(kappa_min)
        dF = dU - T_eff * dS
        return {
            "allowed": dF <= 0.0,
            "dF": dF,
            "dU": dU,
            "dS": dS,
            "T_eff": T_eff,
            "kappa_min": kappa_min,
        }


__all__ = ["ThermodynamicRiskGate"]
