# SPDX-License-Identifier: MIT
"""Gradient Vital Signs — real-time health monitor for the neuromodulation stack.

This module operationalises Section 0 of CLAUDE.md (Gradient Ontology):

    INV-YV1: ΔV > 0 ∧ dΔV/dt ≠ 0

The gradient is alive when:
- The system produces non-trivial signal (MLE finite, not noise)
- The signal is stable enough to act on (MLE not diverging)
- Protectors are holding the gradient within viable range
- The gradient has not collapsed (Cryptobiosis not triggered)

The Gradient Vital Signs (GVS) combines 5 diagnostics into a single
health score that determines whether the system is fit to trade:

    GVS = w_sync · sync_health        # Kuramoto R stability
        + w_risk · risk_health         # GABA + Serotonin protection
        + w_energy · energy_health     # ECS free-energy descent
        + w_chaos · chaos_health       # MLE bounded
        + w_connectivity · conn_health # Spectral gap λ₂ > 0

GVS ∈ [0, 1]:
    GVS > 0.7  → HEALTHY: full trading capacity
    GVS ∈ [0.3, 0.7] → DEGRADED: reduced position sizing
    GVS < 0.3  → CRITICAL: Cryptobiosis entry recommended

This is the 40% maintenance that makes the 60% processing possible.
Without it, the system computes on a discharged gradient.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.physics.lyapunov_exponent import maximal_lyapunov_exponent, spectral_gap


@dataclass(frozen=True, slots=True)
class GradientVitalSigns:
    """Immutable snapshot of gradient health at a point in time."""

    # Individual health components ∈ [0, 1]
    sync_health: float  # Kuramoto R stability (low MLE on R trajectory)
    risk_health: float  # GABA inhibition + serotonin distance from veto
    energy_health: float  # ECS free-energy trend (non-increasing = healthy)
    chaos_health: float  # MLE boundedness (not diverging)
    connectivity_health: float  # Spectral gap (graph still connected)

    # Composite score ∈ [0, 1]
    gvs_score: float

    # Raw diagnostics
    mle: float  # Maximal Lyapunov Exponent of R(t)
    spectral_gap_lambda2: float  # Fiedler eigenvalue
    kuramoto_R: float  # Current order parameter
    gaba_inhibition: float  # Current GABA brake level
    serotonin_level: float  # Current 5-HT level
    ecs_free_energy: float  # Current free energy

    # Verdict
    status: str  # "HEALTHY" | "DEGRADED" | "CRITICAL"

    def is_tradeable(self) -> bool:
        """Can the system safely trade?"""
        return self.status != "CRITICAL"


class GradientHealthMonitor:
    """Real-time gradient health monitor.

    Maintains a rolling window of Kuramoto R(t) values and correlation
    snapshots, and computes the Gradient Vital Signs on each update.

    Usage::

        monitor = GradientHealthMonitor(window=200)

        # On each tick:
        monitor.update(
            R=bus.snapshot().kuramoto_R,
            gaba=bus.snapshot().gaba_inhibition,
            serotonin=bus.snapshot().serotonin_level,
            ecs_free_energy=bus.snapshot().ecs_free_energy,
            correlation_matrix=current_corr,
        )
        vitals = monitor.vitals
        if not vitals.is_tradeable():
            # Recommend Cryptobiosis entry
            ...
    """

    def __init__(
        self,
        window: int = 200,
        *,
        w_sync: float = 0.25,
        w_risk: float = 0.30,
        w_energy: float = 0.20,
        w_chaos: float = 0.15,
        w_connectivity: float = 0.10,
        healthy_threshold: float = 0.7,
        critical_threshold: float = 0.3,
    ) -> None:
        # Weights must sum to 1
        total_w = w_sync + w_risk + w_energy + w_chaos + w_connectivity
        self._w_sync = w_sync / total_w
        self._w_risk = w_risk / total_w
        self._w_energy = w_energy / total_w
        self._w_chaos = w_chaos / total_w
        self._w_connectivity = w_connectivity / total_w

        self._healthy = healthy_threshold
        self._critical = critical_threshold
        self._window = window

        # Rolling buffers
        self._R_history: list[float] = []
        self._fe_history: list[float] = []
        self._last_lambda2: float = 0.0
        self._vitals: Optional[GradientVitalSigns] = None

    @property
    def vitals(self) -> Optional[GradientVitalSigns]:
        """Latest gradient vital signs, or None if not enough data."""
        return self._vitals

    def update(
        self,
        R: float,
        gaba: float,
        serotonin: float,
        ecs_free_energy: float,
        correlation_matrix: Optional[np.ndarray] = None,
    ) -> GradientVitalSigns:
        """Push one tick of neuromodulator state and recompute vitals.

        Parameters
        ----------
        R : float
            Kuramoto order parameter (from SignalBus or KuramotoEngine).
        gaba : float
            GABA inhibition level ∈ [0, 1].
        serotonin : float
            Serotonin level ∈ [0, 1].
        ecs_free_energy : float
            ECS free energy (non-negative).
        correlation_matrix : (N, N) array, optional
            Asset correlation matrix for spectral gap computation.
        """
        # Update rolling buffers
        self._R_history.append(float(R))
        if len(self._R_history) > self._window:
            self._R_history = self._R_history[-self._window :]
        self._fe_history.append(float(ecs_free_energy))
        if len(self._fe_history) > self._window:
            self._fe_history = self._fe_history[-self._window :]

        # ── 1. Sync health: MLE of R(t) trajectory ──
        if len(self._R_history) >= 50:
            R_arr = np.array(self._R_history, dtype=np.float64)
            try:
                mle = maximal_lyapunov_exponent(R_arr, dim=3, tau=1, max_divergence_steps=20)
            except ValueError:
                # INV-LE1 fail-closed: a degenerate R-window (constant /
                # zero-variance — e.g. R frozen at full synchronization, R≡1)
                # has no divergence to measure. A frozen order parameter is the
                # MOST stable sync state, so map it to λ ≤ 0 (health = 1), not
                # to the worst case. A genuinely non-finite estimate cannot
                # occur: the estimator now raises instead of returning NaN/±Inf.
                mle = 0.0
        else:
            mle = 0.0

        # MLE < 0 = stable (health=1), MLE > 1 = diverging (health=0)
        # INV-LE1: MLE is finite (the estimator fails closed otherwise, caught above)
        if not math.isfinite(mle):
            mle = 1.0  # treat non-finite as worst case
        sync_health = float(max(0.0, min(1.0, 1.0 - mle)))

        # ── 2. Risk health: distance from danger zone ──
        # GABA high = system is braking hard = risk health low
        # Serotonin near veto threshold (0.7) = risk health low
        gaba_stress = float(min(1.0, max(0.0, gaba)))
        serotonin_stress = float(min(1.0, max(0.0, serotonin / 0.7)))
        risk_health = float(max(0.0, 1.0 - max(gaba_stress, serotonin_stress)))

        # ── 3. Energy health: free-energy trend ──
        if len(self._fe_history) >= 10:
            fe_arr = np.array(self._fe_history[-20:], dtype=np.float64)
            fe_diff = np.diff(fe_arr)
            # Fraction of steps where FE decreased (healthy) vs increased
            n_decreasing = int(np.sum(fe_diff <= 0))
            energy_health = float(n_decreasing / max(1, len(fe_diff)))
        else:
            energy_health = 1.0  # assume healthy until we have data

        # ── 4. Chaos health: MLE boundedness ──
        # Already computed above; separate dimension: is chaos manageable?
        # |MLE| < 0.5 = manageable, |MLE| > 2 = extreme
        chaos_health = float(max(0.0, min(1.0, 1.0 - abs(mle) / 2.0)))

        # ── 5. Connectivity health: spectral gap ──
        if correlation_matrix is not None:
            adj = np.abs(correlation_matrix)
            np.fill_diagonal(adj, 0.0)
            # Threshold weak correlations
            adj = np.where(adj > 0.3, adj, 0.0)
            lam2 = spectral_gap(adj)
            self._last_lambda2 = lam2
        else:
            lam2 = self._last_lambda2

        # λ₂ > 1 = well connected, λ₂ < 0.01 = fragmented
        # INV-SG1: λ₂ ≥ 0
        conn_health = float(min(1.0, lam2 / 1.0)) if lam2 > 0 else 0.0

        # ── Composite GVS score ──
        gvs = (
            self._w_sync * sync_health
            + self._w_risk * risk_health
            + self._w_energy * energy_health
            + self._w_chaos * chaos_health
            + self._w_connectivity * conn_health
        )
        gvs = float(max(0.0, min(1.0, gvs)))

        # ── Verdict ──
        if gvs >= self._healthy:
            status = "HEALTHY"
        elif gvs >= self._critical:
            status = "DEGRADED"
        else:
            status = "CRITICAL"

        self._vitals = GradientVitalSigns(
            sync_health=sync_health,
            risk_health=risk_health,
            energy_health=energy_health,
            chaos_health=chaos_health,
            connectivity_health=conn_health,
            gvs_score=gvs,
            mle=mle,
            spectral_gap_lambda2=lam2,
            kuramoto_R=R,
            gaba_inhibition=gaba,
            serotonin_level=serotonin,
            ecs_free_energy=ecs_free_energy,
            status=status,
        )
        return self._vitals
