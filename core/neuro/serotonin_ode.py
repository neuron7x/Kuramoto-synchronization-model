# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Serotonin ODE System with Lyapunov Stability.

Implements a biologically-grounded two-state ODE for serotonin (5-HT)
dynamics including receptor desensitisation, solved with 4th-order
Runge-Kutta and equipped with a Lyapunov stability certificate.

State variables:
    level          — 5-HT concentration (∈ [0, 1])
    desensitization — receptor adaptation (∈ [0, ∞), practically bounded)

ODE system:
    d(level)/dt  = -α·level + β·stress + γ·(baseline - level) - δ·desens
    d(desens)/dt =  η·max(0, level - threshold) - μ·desens

Lyapunov function:
    V(level, desens) = 0.5·(level - target)² + λ·desens²
    dV/dt < 0  ⟹  asymptotic stability toward (target, 0)

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SerotoninODEParams:
    """Default parameters for the serotonin ODE system."""

    alpha: float = 0.1  # 5-HT decay rate
    beta: float = 0.3  # stress → 5-HT production rate
    gamma: float = 0.05  # homeostatic pull toward baseline
    delta: float = 0.02  # desensitisation → suppression of 5-HT
    eta: float = 0.01  # 5-HT above threshold → desensitisation
    mu: float = 0.005  # desensitisation recovery rate
    baseline: float = 0.3  # homeostatic target for 5-HT level
    threshold: float = 0.5  # level above which desens increases
    target: float = 0.3  # Lyapunov target level
    lambda_: float = 0.5  # Lyapunov weight on desens term


class SerotoninODE:
    """Two-state ODE for serotonin dynamics with RK4 integration.

    Parameters
    ----------
    params : SerotoninODEParams | None
        ODE parameters.  Uses defaults if *None*.
    level : float
        Initial 5-HT concentration (default: baseline).
    desensitization : float
        Initial receptor desensitisation (default 0.0).
    """

    def __init__(
        self,
        params: SerotoninODEParams | None = None,
        level: float | None = None,
        desensitization: float = 0.0,
    ) -> None:
        self.p = params or SerotoninODEParams()
        self.level = level if level is not None else self.p.baseline
        self.desensitization = desensitization

    # ── ODE right-hand side ──────────────────────────────────────────

    def _derivatives(
        self,
        level: float,
        desens: float,
        stress: float,
    ) -> tuple[float, float]:
        """Compute (d_level/dt, d_desens/dt).

        The level equation combines decay and homeostatic pull into a
        single restoring force so that the equilibrium under zero stress
        and zero desensitisation is exactly ``baseline``::

            d(level)/dt = -(alpha + gamma) * (level - baseline)
                          + beta * stress
                          - delta * desens
        """
        p = self.p
        d_level = -(p.alpha + p.gamma) * (level - p.baseline) + p.beta * stress - p.delta * desens
        d_desens = p.eta * max(0.0, level - p.threshold) - p.mu * desens
        return d_level, d_desens

    # ── RK4 integration step ─────────────────────────────────────────

    def step(self, stress: float, dt: float = 1.0) -> tuple[float, float]:
        """Advance the ODE by *dt* using 4th-order Runge-Kutta.

        Order caveat (stated honestly): the desensitisation RHS carries a
        ``max(0, level - threshold)`` term, so the vector field is only C⁰ — it has
        a kink at ``level = threshold``. RK4's formal 4th-order local accuracy
        assumes a C⁴ field, so on any step that *crosses* the threshold the local
        order degrades (toward ~1–2); full 4th order is attained only on steps that
        stay entirely below or entirely above the threshold. RK4 is still strictly
        more accurate than explicit Euler here (most of a trajectory is smooth), but
        do not read the "4th-order" label as a crossing-uniform guarantee. A
        crossing-aware sub-stepping integrator would restore uniform order if that
        precision is ever required.

        Parameters
        ----------
        stress : float
            Current stress input (non-negative).
        dt : float
            Integration time step.

        Returns
        -------
        tuple[float, float]
            (level, desensitization) after the step.
        """
        y1, y2 = self.level, self.desensitization

        k1a, k1b = self._derivatives(y1, y2, stress)
        k2a, k2b = self._derivatives(y1 + 0.5 * dt * k1a, y2 + 0.5 * dt * k1b, stress)
        k3a, k3b = self._derivatives(y1 + 0.5 * dt * k2a, y2 + 0.5 * dt * k2b, stress)
        k4a, k4b = self._derivatives(y1 + dt * k3a, y2 + dt * k3b, stress)

        self.level = y1 + (dt / 6.0) * (k1a + 2 * k2a + 2 * k3a + k4a)
        self.desensitization = y2 + (dt / 6.0) * (k1b + 2 * k2b + 2 * k3b + k4b)

        # Clamp level to [0, 1] for biological plausibility
        self.level = max(
            0.0, min(1.0, self.level)
        )  # INV-5HT1: s(t) ∈ [0,1] — bounded output (biological 5-HT range)
        # Desensitization is non-negative
        self.desensitization = max(
            0.0, self.desensitization
        )  # bounds: desensitization ≥ 0 — receptor-adaptation state lower bound
        # (INV-5HT4 governs *sensitivity* ∈ [0.1,1] in the controller, not this state)

        return self.level, self.desensitization

    # ── Lyapunov stability verification ──────────────────────────────

    def _lyapunov(self, level: float, desens: float) -> float:
        """Compute Lyapunov function V(level, desens)."""
        p = self.p
        return 0.5 * (level - p.target) ** 2 + p.lambda_ * desens**2

    def lyapunov_parameter_certificate(self) -> bool:
        """Analytical stability certificate for the *unforced* flow.

        This is the certificate ``verify_lyapunov`` is *not*: it proves, from the
        parameters alone, that V is a strict Lyapunov function for the equilibrium
        (baseline, 0) — rather than merely observing that one clamped trajectory
        happened to descend.

        With ``target == baseline`` and letting ``e = level - baseline``, on the
        sub-threshold region (level ≤ threshold, so the desensitisation forcing
        ``max(0, level-threshold)`` vanishes) and zero stress::

            dV/dt = -[ (α+γ)·e²  +  δ·e·d  +  2λμ·d² ]

        which is negative-definite iff the symmetric form
        ``M = [[α+γ, δ/2], [δ/2, 2λμ]]`` is positive-definite, i.e.

            α+γ > 0   and   (α+γ)·(2λμ) > (δ/2)².

        Scope (stated honestly, not overclaimed): guarantees local asymptotic
        stability of (baseline, 0) for the zero-stress flow while level ≤ threshold.
        Above threshold the desensitisation coupling ``+2λη·d·(level-threshold)``
        can inject energy; the homeostatic pull returns the state below threshold
        for bounded stress, but that regime is outside this closed-form guarantee.
        Returns False (rather than a false certificate) when target ≠ baseline,
        since V is then not centred on the equilibrium.
        """
        p = self.p
        if p.target != p.baseline:
            return False
        a = p.alpha + p.gamma
        if a <= 0.0:
            return False
        return a * (2.0 * p.lambda_ * p.mu) > (p.delta / 2.0) ** 2

    def verify_lyapunov(
        self,
        trajectory: list[tuple[float, float]],
    ) -> bool:
        """Check empirical energy monotonicity along a *given* trajectory.

        Returns True iff V(t+1) ≤ V(t) for every consecutive pair of the supplied
        states. This is a necessary witness of descent, **not** a proof that V is a
        Lyapunov function — the states are already clamped to [0,1]×[0,∞) by
        ``step``, so at saturation a clamp can inject energy and make V rise for a
        flow that is nonetheless stable, and a single descending trajectory says
        nothing about other initial conditions. For the analytical guarantee use
        ``lyapunov_parameter_certificate``; use this to falsify a claimed descent on
        a concrete run (e.g. as a positive/negative physics-witness control).

        Parameters
        ----------
        trajectory : list[tuple[float, float]]
            Sequence of (level, desensitization) states.

        Returns
        -------
        bool
            True if V is non-increasing along the entire trajectory (within
            numerical tolerance).
        """
        if len(trajectory) < 2:
            return True

        eps = 1e-12  # numerical tolerance
        prev_v = self._lyapunov(*trajectory[0])
        for state in trajectory[1:]:
            curr_v = self._lyapunov(*state)
            if curr_v > prev_v + eps:
                return False
            prev_v = curr_v
        return True
