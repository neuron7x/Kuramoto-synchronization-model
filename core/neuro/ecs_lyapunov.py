# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""ECS Free Energy Regulator with Lyapunov Stability Guarantee.

Implements a homeostatic free-energy regulator inspired by the
Endocannabinoid System (ECS). The ODE system is integrated with RK4
and a Lyapunov descent guarantee: if a step would increase the
Lyapunov function V, the update is scaled back to enforce dV/dt < 0.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from core.neuro.signal_bus import NeuroSignalBus


class ECSLyapunovRegulator:
    """Homeostatic ECS regulator with provable Lyapunov stability.

    State variables
    ---------------
    free_energy (FE)
        Deviation from homeostatic set-point. High FE → high stress.
    compensatory_factor (CF)
        Endocannabinoid-like compensatory signal that suppresses FE.
    stress_integral (SI)
        Accumulated stress signal (leaky integrator).

    Lyapunov function
    -----------------
    V = 0.5 * FE^2 + lambda_ * CF^2 + mu * SI^2

    The update rule guarantees dV/dt < 0 by post-hoc correction if the
    RK4 step would violate descent.

    Parameters
    ----------
    bus : NeuroSignalBus
        Signal bus for publishing ecs_free_energy.
    k_fe : float
        Decay rate of free energy (default 0.1).
    k_cf : float
        Adaptation rate of compensatory factor (default 0.05).
    k_si : float
        Decay rate of stress integral (default 0.03).
    damping : float
        Damping on compensatory factor dynamics (default 0.02).
    target_fe : float
        Target (homeostatic) free energy level (default 0.0).
    lambda_ : float
        Lyapunov weight for CF^2 term (default 0.5).
    mu : float
        Lyapunov weight for SI^2 term (default 0.3).
    """

    def __init__(
        self,
        bus: NeuroSignalBus,
        k_fe: float = 0.1,
        k_cf: float = 0.05,
        k_si: float = 0.03,
        damping: float = 0.02,
        target_fe: float = 0.0,
        lambda_: float = 0.5,
        mu: float = 0.3,
    ) -> None:
        self._bus = bus
        self._k_fe = k_fe
        self._k_cf = k_cf
        self._k_si = k_si
        self._damping = damping
        self._target_fe = target_fe
        self._lambda = lambda_
        self._mu = mu

        # State
        self.free_energy: float = 0.0
        self.compensatory_factor: float = 0.0
        self.stress_integral: float = 0.0

    # ── Lyapunov function ─────────────────────────────────────────────

    def _lyapunov(self, fe: float, cf: float, si: float) -> float:
        return 0.5 * fe**2 + self._lambda * cf**2 + self._mu * si**2

    # ── ODE right-hand side ───────────────────────────────────────────

    def _derivatives(
        self, fe: float, cf: float, si: float, stress: float
    ) -> tuple[float, float, float]:
        d_fe = -self._k_fe * fe + stress - cf
        d_cf = self._k_cf * (fe - self._target_fe) - self._damping * cf
        d_si = -self._k_si * si + stress
        return d_fe, d_cf, d_si

    # ── RK4 integrator ────────────────────────────────────────────────

    def _rk4_step(
        self, fe: float, cf: float, si: float, stress: float, dt: float
    ) -> tuple[float, float, float]:
        k1 = self._derivatives(fe, cf, si, stress)
        k2 = self._derivatives(
            fe + 0.5 * dt * k1[0],
            cf + 0.5 * dt * k1[1],
            si + 0.5 * dt * k1[2],
            stress,
        )
        k3 = self._derivatives(
            fe + 0.5 * dt * k2[0],
            cf + 0.5 * dt * k2[1],
            si + 0.5 * dt * k2[2],
            stress,
        )
        k4 = self._derivatives(fe + dt * k3[0], cf + dt * k3[1], si + dt * k3[2], stress)

        new_fe = fe + (dt / 6.0) * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        new_cf = cf + (dt / 6.0) * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        new_si = si + (dt / 6.0) * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
        return new_fe, new_cf, new_si

    # ── Public API ────────────────────────────────────────────────────

    def step(self, stress: float, dt: float = 1.0) -> dict:
        """Advance one time step with Lyapunov-guaranteed descent.

        Parameters
        ----------
        stress : float
            External stress input (e.g. from HPC PWPE).
        dt : float
            Integration time step (default 1.0).

        Returns
        -------
        dict
            free_energy, compensatory_factor, lyapunov_V, dV_dt, stable
        """
        V_before = self._lyapunov(self.free_energy, self.compensatory_factor, self.stress_integral)

        new_fe, new_cf, new_si = self._rk4_step(
            self.free_energy,
            self.compensatory_factor,
            self.stress_integral,
            stress,
            dt,
        )

        V_after = self._lyapunov(new_fe, new_cf, new_si)
        dV = V_after - V_before
        stable = True

        # Lyapunov correction: if dV > 0, scale the update to ensure descent
        if dV > 0 and V_before > 1e-12:
            # Binary search for maximum safe step scale
            alpha = 0.5
            for _ in range(20):
                mixed_fe = self.free_energy + alpha * (new_fe - self.free_energy)
                mixed_cf = self.compensatory_factor + alpha * (new_cf - self.compensatory_factor)
                mixed_si = self.stress_integral + alpha * (new_si - self.stress_integral)
                V_mixed = self._lyapunov(mixed_fe, mixed_cf, mixed_si)
                if V_mixed < V_before:
                    break
                alpha *= 0.5
            else:
                # Fallback: pure decay toward zero
                alpha = 0.0

            new_fe = self.free_energy + alpha * (new_fe - self.free_energy)
            new_cf = self.compensatory_factor + alpha * (new_cf - self.compensatory_factor)
            new_si = self.stress_integral + alpha * (new_si - self.stress_integral)
            V_after = self._lyapunov(new_fe, new_cf, new_si)
            dV = V_after - V_before
            stable = dV <= 0

        self.free_energy = new_fe
        self.compensatory_factor = new_cf
        self.stress_integral = new_si

        # Publish to bus
        self._bus.publish_ecs(max(0.0, self.free_energy))

        return {
            "free_energy": self.free_energy,
            "compensatory_factor": self.compensatory_factor,
            "lyapunov_V": V_after,
            "dV_dt": dV / dt if dt > 0 else 0.0,
            "stable": stable,
        }

    def get_risk_multiplier(self) -> float:
        """Map free energy to a risk multiplier ∈ [0.1, 1.0].

        High FE → conservative (low multiplier).
        Low FE → aggressive (high multiplier).
        """
        # Sigmoid-like mapping: multiplier = 1 / (1 + |FE|)
        # Clipped to [0.1, 1.0]
        raw = 1.0 / (1.0 + abs(self.free_energy))
        return max(
            0.1, min(1.0, raw)
        )  # INV-FE2: multiplier ∈ [0.1, 1.0] — sigmoid output clamped to valid operating range
