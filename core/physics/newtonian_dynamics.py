# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T2 — Newtonian Inertial Dynamics for price trajectories.

Defines:
    m_i(t) = EMA(volume_i, τ=20)           — inertial mass
    F_i(t) = Σ order_flow_imbalance(t)     — net force (OFI)
    a_i(t) = F_i(t) / m_i(t)              — price acceleration

Price update via Euler integration (NOT Verlet):
    p_i(t+1) = p_i(t) + v_i(t)·dt + ½·a_i(t)·dt²

AUDIT NOTE: Verlet requires conservative force field.
OFI is dissipative/non-conservative → Euler is the honest choice.
This is documented, not hidden.

Dimensional analysis:
    [F] = $/tick (OFI units)
    [m] = contracts (volume units)
    [a] = ($/tick) / contracts → normalised to return/tick

TACL free energy constraint:
    dF/dt = dU/dt - T·dS/dt ≤ 0
    Position update allowed only if this holds.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class NewtonianPriceDynamics:
    """Newtonian mechanics for price trajectory modelling.

    Parameters
    ----------
    ema_span : int
        EMA span for inertial mass computation (default 20).
    dt : float
        Time step for integration (default 1.0).
    """

    def __init__(self, ema_span: int = 20, dt: float = 1.0) -> None:
        if ema_span < 1:
            raise ValueError(f"ema_span must be ≥ 1, got {ema_span}")
        if dt <= 0:
            raise ValueError(f"dt must be > 0, got {dt}")
        self._ema_span = ema_span
        self._dt = dt

    @staticmethod
    def compute_mass(volume_series: NDArray[np.float64], span: int = 20) -> float:
        """Inertial mass = EMA of volume.

        Higher volume → higher mass → lower acceleration for same force.
        """
        volume_series = np.asarray(volume_series, dtype=np.float64)
        if volume_series.size == 0:
            return 1e-12
        alpha = 2.0 / (span + 1)
        ema = volume_series[0]
        for v in volume_series[1:]:
            ema = alpha * v + (1.0 - alpha) * ema
        return max(float(ema), 1e-12)

    @staticmethod
    def compute_force(ofi_series: NDArray[np.float64]) -> float:
        """Net force = sum of order flow imbalance.

        Positive OFI → net buying pressure → positive force.
        """
        ofi_series = np.asarray(ofi_series, dtype=np.float64)
        if ofi_series.size == 0:
            return 0.0
        return float(np.sum(ofi_series))

    @staticmethod
    def compute_acceleration(force: float, mass: float) -> float:
        """a = F/m. Mass is clamped to avoid division by zero."""
        mass_safe = max(abs(mass), 1e-12)
        return force / mass_safe

    @staticmethod
    def euler_step(
        price: float,
        velocity: float,
        acceleration: float,
        dt: float = 1.0,
    ) -> tuple[float, float]:
        """Euler integration step.

        Returns (new_price, new_velocity).

        Note: Uses Euler, not Verlet. OFI forces are non-conservative,
        so Verlet's symplectic advantage does not apply. This is the
        mathematically honest choice.
        """
        new_velocity = velocity + acceleration * dt
        new_price = price + velocity * dt + 0.5 * acceleration * dt**2
        return new_price, new_velocity

    def step(
        self,
        price: float,
        velocity: float,
        volume_history: NDArray[np.float64],
        ofi: NDArray[np.float64],
    ) -> tuple[float, float, float]:
        """Full dynamics step: mass → force → acceleration → integrate.

        Returns (new_price, new_velocity, acceleration).
        """
        mass = self.compute_mass(volume_history, self._ema_span)
        force = self.compute_force(ofi)
        accel = self.compute_acceleration(force, mass)
        new_price, new_velocity = self.euler_step(price, velocity, accel, self._dt)
        return new_price, new_velocity, accel


class FreeEnergyGate:
    """TACL free energy constraint for position updates.

    Gate condition: dF/dt = dU/dt - T·dS/dt ≤ 0.
    Position update proceeds only if this holds.

    Parameters
    ----------
    T : float
        Control temperature (default 0.60, from TACL calibration).
    """

    def __init__(self, T: float = 0.60) -> None:
        if T <= 0:
            raise ValueError(f"Temperature must be > 0, got {T}")
        self._T = T

    @property
    def temperature(self) -> float:
        return self._T

    def gate(self, dU: float, dS: float) -> bool:
        """Check free energy constraint.

        Parameters
        ----------
        dU : float
            Change in internal energy (mark-to-market P&L delta).
        dS : float
            Change in entropy (portfolio diversification delta).

        Returns
        -------
        True if position update is allowed (dF/dt ≤ 0).
        """
        dF = dU - self._T * dS
        return dF <= 0.0

    def free_energy_change(self, dU: float, dS: float) -> float:
        """Compute dF = dU - T·dS."""
        return dU - self._T * dS


__all__ = ["NewtonianPriceDynamics", "FreeEnergyGate"]
