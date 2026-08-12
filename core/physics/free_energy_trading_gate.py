# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T6 — dF/dt ≤ 0 trading gate with order-book temperature calibration.

Free energy formulation (INV-FE1, INV-FE2):
    F = U - T_LOB(t) · S_q(t)

where:
    U        = portfolio risk exposure (e.g. VaR or weighted drawdown)
    T_LOB(t) = kinetic temperature from order book (Li et al. Entropy 2024)
    S_q(t)   = Tsallis entropy of position weights

Trade admitted only if (INV-FE1):
    ΔF = F_after - F_before ≤ 0

Nondimensional convention (dimensional coherence of F)
------------------------------------------------------
``F = U − T·S`` is only meaningful if its three terms share one unit.
This module works in a *nondimensional* (reduced) unit system, exactly as
reduced-unit molecular dynamics does:

* The Boltzmann scale is set to ``K_B_MARKET = 1.0`` (below). It is the
  market analogue of k_B: the constant that converts a kinetic-energy
  scale into a temperature scale. Fixing it to 1 chooses the energy unit
  to equal the temperature unit, so T, energy, U, and the T·S product are
  all expressed as the SAME pure number. This is the standard reduced-unit
  nondimensionalization, NOT an omission of k_B.
* S_q is dimensionless (nats-like, an entropy per unit k_B).
* U is a risk exposure already expressed in the reduced energy unit.
* Therefore T·S and U are commensurable and ``F`` is a pure number. Both
  ``compute_T_LOB`` branches return a value in this one reduced T-unit, so
  they are mutually consistent (neither is "energy" while the other is
  "dimensionless"): the order-book branch carries k_B explicitly and the
  volatility fallback is already reduced.

T_LOB calibration via equipartition (order book available)
----------------------------------------------------------
Equipartition for ``n_dof`` quadratic degrees of freedom reads
``⟨KE⟩ = (n_dof / 2) · k_B · T``. Solving for the temperature:

    T_LOB = 2 · KE / (n_dof · k_B),   KE = Σ ½·m_i·v_i²

Here each order-book *level* contributes one velocity component, so
``n_dof`` is the number of levels (``v.size``). In reduced units
``k_B = K_B_MARKET = 1.0`` so the implementation reduces to
``T_LOB = 2·KE / n_dof`` — numerically identical to the prior code but now
the equipartition factor is dimensionally correct and the divisor is named
``n_dof`` (a degree-of-freedom count) rather than a bare LOB level count.

When order book not available, falls back to (already reduced/dimensionless):
    T_LOB = (σ / σ_ref)² · T_base

where σ = realised volatility, T_base = 0.60 (TACL calibration).

Calibration band (``is_calibrated``)
------------------------------------
The 5–20% / N≥20 trigger-rate band is an OPERATIONAL HEURISTIC reporting
flag, NOT a physics invariant: it is an aesthetic backtest target (0% ⇒ the
gate is trivially satisfied and useless; near 100% ⇒ the gate is too tight
and the system cannot trade), not a quantity derived from first principles.
It is reported as such by ``GateStatistics.is_calibrated`` and must never be
presented as a thermodynamic law. See that field's docstring.

References:
    Li et al. "Kinetic temperature of order book" Entropy (2024)
    Tsallis "Nonextensive statistics" J. Stat. Phys. (1988)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# Reduced (nondimensional) Boltzmann scale for the market free energy.
# Market analogue of k_B: converts a kinetic-energy scale into a temperature
# scale via equipartition ⟨KE⟩ = (n_dof/2)·k_B·T. Set to 1.0 to work in
# reduced units, so that temperature, energy, U and T·S are all the SAME pure
# number and F = U − T·S is dimensionally coherent. This is an explicit unit
# choice (reduced-unit MD convention), NOT a dropped constant. Changing it
# rescales T by a positive factor and therefore does NOT change the sign of
# ΔF (INV-FE1) nor the non-negativity of components (INV-FE2).
K_B_MARKET: float = 1.0

# INV-FE2: equipartition temperature is ≥ 0 by construction (Σ½m_i v_i² ≥ 0
# for masses m_i ≥ 0). This is the documented physical lower bound for the
# reduced kinetic temperature, used to absorb float underflow to exactly 0
# WITHOUT masking sign errors — negative/non-finite inputs already fail closed
# above this floor (see compute_T_LOB). bounds: reduced-unit ULP floor.
T_LOB_FLOOR: float = 0.0


@dataclass(frozen=True, slots=True)
class FreeEnergyTradeDecision:
    """Decision from free energy trading gate."""

    allowed: bool
    F_before: float
    F_after: float
    delta_F: float
    U_before: float
    U_after: float
    T_LOB: float
    S_q_before: float
    S_q_after: float


@dataclass(frozen=True, slots=True)
class GateStatistics:
    """Gate trigger statistics for validation."""

    total_checks: int
    total_rejected: int
    trigger_rate: float  # rejected / total
    mean_delta_F: float
    is_calibrated: bool
    """Operational heuristic flag, NOT physics.

    True iff 5% ≤ trigger_rate ≤ 20% over ≥ 20 checks. This band is an
    aesthetic backtest-usefulness target (a trivially-satisfied gate at 0%
    is useless; a near-100% gate is untradeable), not a first-principles
    invariant. Never report it as a thermodynamic law. See the module
    docstring "Calibration band" section.
    """


class FreeEnergyTradingGate:
    """Thermodynamic trading gate: ΔF ≤ 0 required for trade admission.

    Parameters
    ----------
    T_base : float
        Base temperature when LOB data unavailable (default 0.60).
    q : float
        Tsallis entropic index (default 1.5).
    vol_reference : float
        Reference volatility for temperature scaling (default 0.01).
    """

    def __init__(
        self,
        T_base: float = 0.60,
        q: float = 1.5,
        vol_reference: float = 0.01,
    ) -> None:
        if T_base <= 0:
            raise ValueError(f"T_base must be > 0, got {T_base}")
        if q <= 1.0:
            raise ValueError(f"q must be > 1.0, got {q}")
        if vol_reference <= 0:
            raise ValueError(f"vol_reference must be > 0, got {vol_reference}")
        self._T_base = T_base
        self._q = q
        self._vol_ref = vol_reference
        self._total_checks = 0
        self._total_rejected = 0
        self._delta_F_history: list[float] = []

    @property
    def T_base(self) -> float:
        return self._T_base

    def compute_T_LOB(
        self,
        order_book_velocities: NDArray[np.float64] | None = None,
        order_book_sizes: NDArray[np.float64] | None = None,
        realized_volatility: float | None = None,
    ) -> float:
        """Compute the reduced LOB kinetic temperature (equipartition).

        If order book data available, by equipartition over ``n_dof``
        quadratic degrees of freedom (one velocity component per level),
        ``⟨KE⟩ = (n_dof/2)·k_B·T`` ⇒

            T_LOB = 2 · KE / (n_dof · k_B),   KE = Σ ½·m_i·v_i²

        with ``k_B = K_B_MARKET`` and ``n_dof = number of order-book levels``.
        Returned in the reduced T-unit (see module docstring).

        Otherwise fallback (already reduced/dimensionless):
            T_LOB = (σ/σ_ref)² · T_base

        Returns a value ≥ 0 (INV-FE2).
        """
        if order_book_velocities is not None and order_book_sizes is not None:
            v = np.asarray(order_book_velocities, dtype=np.float64)
            m = np.asarray(order_book_sizes, dtype=np.float64)
            if v.size == 0:
                return self._T_base
            # INV-FE2: order-book sizes are masses ≥ 0; reject negative input
            # rather than letting a negative kinetic energy be silently floored.
            if not (
                bool(np.all(np.isfinite(v)))
                and bool(np.all(np.isfinite(m)))
                and bool(np.all(m >= 0.0))
            ):
                raise ValueError("INV-FE2: order_book_sizes must be finite and ≥ 0 (masses)")
            # Equipartition: each level is one quadratic DOF, so n_dof = v.size.
            n_dof = max(v.size, 1)
            kinetic = 0.5 * np.sum(m * v**2)
            T = 2.0 * kinetic / (n_dof * K_B_MARKET)
            # INV-FE2: reduced kinetic temperature is ≥ 0 (Σ½m_i v_i² ≥ 0 for
            # m_i ≥ 0, already enforced above). Clamp absorbs float underflow
            # to the documented physical lower bound; it does NOT mask a sign
            # error because negative input fails closed above. bounds: T_LOB_FLOOR.
            return max(float(T), T_LOB_FLOOR)

        if realized_volatility is not None:
            # INV-FE2: realized volatility is non-negative (σ ≥ 0).
            if not (np.isfinite(realized_volatility) and realized_volatility >= 0.0):
                raise ValueError(
                    f"INV-FE2: realized_volatility must be finite and ≥ 0, got {realized_volatility}"
                )
            # Already in the reduced T-unit: (σ/σ_ref)² is dimensionless and
            # T_base is a reduced temperature, so this is consistent with the
            # equipartition branch (both return the same reduced unit).
            ratio = realized_volatility / self._vol_ref
            return self._T_base * ratio**2

        return self._T_base

    def tsallis_entropy(self, weights: NDArray[np.float64]) -> float:
        """S_q = (1 - Σ w_i^q) / (q-1) on normalised position weights.

        Fail-closed (INV-FE2): the Tsallis entropy is non-negative for q>1 on
        the probability simplex (Tsallis 1988) — a theorem, not a fluctuation.
        Non-finite weights are rejected (rather than returning a silent NaN that
        the ``total < 1e-12`` guard cannot catch, since ``NaN < 1e-12`` is
        False), and a materially negative S_q is treated as an
        implementation/parameter bug (raise) rather than clamped away.
        """
        w = np.abs(np.asarray(weights, dtype=np.float64))
        if not bool(np.all(np.isfinite(w))):
            raise ValueError("INV-FE2: position weights must be finite (no NaN/Inf)")
        total = float(w.sum())
        if total < 1e-12:
            # Degenerate (no position mass): entropy is identically zero.
            return 0.0
        w = w / total
        s_q = (1.0 - float(np.sum(w**self._q))) / (self._q - 1.0)
        # INV-FE2: S_q ≥ 0 for q>1 on the simplex; tolerate float round-off only.
        if s_q < -1e-12:
            raise ValueError(
                f"INV-FE2: Tsallis entropy S_q={s_q:.3e} < 0 for q={self._q} on the "
                f"simplex — a formula/implementation bug, not a fluctuation."
            )
        return max(0.0, s_q)

    def compute_risk_exposure(
        self,
        positions: NDArray[np.float64],
        returns: NDArray[np.float64],
    ) -> float:
        """Portfolio risk exposure U = Σ|pos_i| · |ret_i| (simple VaR proxy)."""
        pos = np.abs(np.asarray(positions, dtype=np.float64))
        ret = np.abs(np.asarray(returns, dtype=np.float64))
        if pos.shape != ret.shape:
            raise ValueError(f"Shape mismatch: {pos.shape} vs {ret.shape}")
        return float(np.sum(pos * ret))

    def check(
        self,
        positions_before: NDArray[np.float64],
        positions_after: NDArray[np.float64],
        recent_returns: NDArray[np.float64],
        T_LOB: float | None = None,
        realized_volatility: float | None = None,
    ) -> FreeEnergyTradeDecision:
        """Check if trade (position change) satisfies ΔF ≤ 0.

        Parameters
        ----------
        positions_before : (N,) current positions.
        positions_after : (N,) proposed positions.
        recent_returns : (N,) recent asset returns.
        T_LOB : float, order-book temperature (if pre-computed).
        realized_volatility : float, for temperature fallback.

        Returns
        -------
        FreeEnergyTradeDecision.
        """
        pos_before = np.asarray(positions_before, dtype=np.float64)
        pos_after = np.asarray(positions_after, dtype=np.float64)
        returns = np.asarray(recent_returns, dtype=np.float64)

        # Temperature
        if T_LOB is None:
            T_LOB = self.compute_T_LOB(realized_volatility=realized_volatility)
        # INV-FE2: the temperature component must be finite and ≥ 0 (a negative
        # temperature is unphysical and would invert the ΔF entropy term).
        if not (np.isfinite(T_LOB) and T_LOB >= 0.0):
            raise ValueError(f"INV-FE2: T_LOB must be finite and ≥ 0, got {T_LOB}")

        # Risk exposure
        U_before = self.compute_risk_exposure(pos_before, returns)
        U_after = self.compute_risk_exposure(pos_after, returns)

        # Entropy
        S_before = self.tsallis_entropy(pos_before)
        S_after = self.tsallis_entropy(pos_after)

        # Free energy
        F_before = U_before - T_LOB * S_before
        F_after = U_after - T_LOB * S_after
        delta_F = F_after - F_before

        allowed = delta_F <= 0.0
        self._total_checks += 1
        if not allowed:
            self._total_rejected += 1
        self._delta_F_history.append(delta_F)

        return FreeEnergyTradeDecision(
            allowed=bool(allowed),
            F_before=F_before,
            F_after=F_after,
            delta_F=delta_F,
            U_before=U_before,
            U_after=U_after,
            T_LOB=T_LOB,
            S_q_before=S_before,
            S_q_after=S_after,
        )

    def statistics(self) -> GateStatistics:
        """Get gate trigger statistics for calibration validation."""
        total = self._total_checks
        rejected = self._total_rejected
        rate = rejected / max(total, 1)
        mean_dF = float(np.mean(self._delta_F_history)) if self._delta_F_history else 0.0
        return GateStatistics(
            total_checks=total,
            total_rejected=rejected,
            trigger_rate=rate,
            mean_delta_F=mean_dF,
            # bounds: operational heuristic, NOT physics. 5–20% trigger band
            # over ≥ 20 checks is an aesthetic backtest-usefulness target (see
            # GateStatistics.is_calibrated docstring + module "Calibration band").
            is_calibrated=0.05 <= rate <= 0.20 if total >= 20 else False,
        )

    def reset_statistics(self) -> None:
        """Reset gate counters."""
        self._total_checks = 0
        self._total_rejected = 0
        self._delta_F_history.clear()


__all__ = [
    "FreeEnergyTradingGate",
    "FreeEnergyTradeDecision",
    "GateStatistics",
    "K_B_MARKET",
    "T_LOB_FLOOR",
]
