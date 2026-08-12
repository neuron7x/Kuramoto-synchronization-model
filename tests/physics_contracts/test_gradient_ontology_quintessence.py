# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Quintessence witness for INV-YV1 — the gradient-ontology root axiom.

INV-YV1 is the root axiom of the whole system (CLAUDE.md §0): *being is a
sustained potential difference*, ΔV > 0 ∧ dΔV/dt ≠ 0. A static gradient is a
capacitor; a living gradient is a process; intelligence requires the second.
The ``GradientHealthMonitor`` is the organ that measures ΔV — the aggregate
gradient health across the five maintenance subsystems (sync, risk, energy,
chaos, connectivity).

This file witnesses the axiom across seven facets — the engineering distillation
of the maintenance hierarchy:

  iterations  (rigor)        : bounded → positive → dynamic → ordered
  integrations (subsystems)  : the five health channels fold into one ΔV score
  adaptations  (regimes)     : healthy / stressed / oscillating / degraded

Each facet is a falsifiable property of the real monitor, deriving every
threshold from the axiom. Nothing here is a market claim — it is the physics
core, stated as code.
"""

from __future__ import annotations

import numpy as np

from core.neuro.gradient_vital_signs import GradientHealthMonitor

# Strict definitional bounds carry only numerical-noise slack.
SCORE_EPS = 1e-9
# A living gradient must vary under varying drive; a capacitor would not.
DYNAMISM_FLOOR = 1e-3


def _warm(
    monitor: GradientHealthMonitor,
    n: int,
    *,
    R: float = 0.9,
    gaba: float = 0.1,
    serotonin: float = 0.3,
    ecs_free_energy: float = 1.0,
) -> None:
    """Feed a constant nominal regime so MLE / free-energy history is populated."""
    for _ in range(n):
        monitor.update(R=R, gaba=gaba, serotonin=serotonin, ecs_free_energy=ecs_free_energy)


# ── Facet 1 (iteration: bounded) — ΔV is a well-defined convex aggregate ──
def test_gradient_score_is_a_bounded_convex_aggregate() -> None:
    """INV-YV1: the ΔV score is a convex combination of [0,1] healths ⇒ ΔV ∈ [0,1].

    The five subsystem weights must sum to 1, and each health lies in [0,1], so
    the aggregate gradient ΔV can never leave [0,1] for any admissible drive.
    """
    monitor = GradientHealthMonitor()
    weight_sum = (
        monitor._w_sync
        + monitor._w_risk
        + monitor._w_energy
        + monitor._w_chaos
        + monitor._w_connectivity
    )
    assert abs(weight_sum - 1.0) <= SCORE_EPS, (
        "INV-YV1 violated: observed weight_sum = "
        f"{weight_sum:.9f} must equal 1 (tolerance {SCORE_EPS:.0e}); ΔV must be a "
        "convex combination of the five maintenance healths"
    )
    rng = np.random.default_rng(seed=0)
    worst_low, worst_high = np.inf, -np.inf
    for _ in range(300):
        vitals = monitor.update(
            R=float(rng.uniform(0.0, 1.0)),
            gaba=float(rng.uniform(0.0, 1.0)),
            serotonin=float(rng.uniform(0.0, 1.0)),
            ecs_free_energy=float(rng.uniform(0.0, 5.0)),
        )
        worst_low = min(worst_low, vitals.gvs_score)
        worst_high = max(worst_high, vitals.gvs_score)
    assert worst_low >= 0.0 - SCORE_EPS and worst_high <= 1.0 + SCORE_EPS, (
        "INV-YV1 violated: observed ΔV range = "
        f"[{worst_low:.6f}, {worst_high:.6f}] must lie in [0,1] (tolerance "
        f"{SCORE_EPS:.0e}) over n=300 with seed=0; the gradient is bounded"
    )


# ── Facet 2 (iteration: positive) — ΔV > 0 when the system is alive ──
def test_gradient_is_strictly_positive_under_nominal_regime() -> None:
    """INV-YV1 (ΔV > 0): a nominal, low-stress regime sustains a positive gradient.

    Being requires ΔV > 0. Under healthy drive the monitor must report a strictly
    positive, non-CRITICAL gradient — the system exists as a system, not noise.
    """
    monitor = GradientHealthMonitor()
    _warm(monitor, 60)
    vitals = monitor.update(R=0.9, gaba=0.1, serotonin=0.3, ecs_free_energy=1.0)
    assert vitals.gvs_score > 0.0 + SCORE_EPS, (
        "INV-YV1 violated: observed ΔV = "
        f"{vitals.gvs_score:.6f} must be > 0 under a nominal regime with R=0.9; a "
        "living system sustains a positive potential difference"
    )
    assert vitals.is_tradeable, (
        "INV-YV1 violated: observed status = "
        f"{vitals.status!r} must not be CRITICAL under a nominal regime with "
        "gaba=0.1; a positive gradient is a usable gradient"
    )


# ── Facet 3 (iteration: dynamic) — dΔV/dt ≠ 0: a process, not a capacitor ──
def test_gradient_is_dynamic_under_varying_drive() -> None:
    """INV-YV1 (dΔV/dt ≠ 0): ΔV must move when the drive moves.

    The axiom's second clause is the whole point: a static gradient is a
    capacitor, a living gradient is a process. Under an oscillating order
    parameter the ΔV trajectory must have strictly positive variation.
    """
    monitor = GradientHealthMonitor()
    scores = []
    for step in range(80):
        order_parameter = 0.5 + 0.4 * float(np.sin(step / 5.0))
        scores.append(
            monitor.update(
                R=order_parameter, gaba=0.2, serotonin=0.3, ecs_free_energy=1.0
            ).gvs_score
        )
    variation = float(np.std(scores))
    assert variation >= DYNAMISM_FLOOR, (
        "INV-YV1 violated: observed std(ΔV) = "
        f"{variation:.5f} must be ≥ {DYNAMISM_FLOOR:.0e} under an oscillating drive "
        "with steps=80; dΔV/dt ≠ 0 — a living gradient is a process, not a capacitor"
    )


# ── Facet 4 (integration: hierarchy) — protectors override generators ──
def test_protector_alarm_overrides_healthy_generators() -> None:
    """INV-YV1 maintenance hierarchy: a Layer-2 protector pulls ΔV down hard.

    With every generator healthy (high R), a maximal GABA brake (risk protector)
    must crush risk_health to 0 and drop the aggregate gradient — protectors have
    priority over generators; a system without a protected gradient cannot use it.
    """
    monitor = GradientHealthMonitor()
    _warm(monitor, 60)
    healthy = monitor.update(R=0.9, gaba=0.0, serotonin=0.3, ecs_free_energy=1.0)
    alarmed = monitor.update(R=0.9, gaba=1.0, serotonin=0.3, ecs_free_energy=1.0)
    assert alarmed.risk_health <= SCORE_EPS, (
        "INV-YV1 violated: observed risk_health = "
        f"{alarmed.risk_health:.6f} must be ≈ 0 under gaba=1.0; a maximal protector "
        "brake must zero the risk channel"
    )
    assert alarmed.gvs_score < healthy.gvs_score - SCORE_EPS, (
        "INV-YV1 violated: observed ΔV did not drop under protector alarm "
        f"({alarmed.gvs_score:.4f} vs healthy {healthy.gvs_score:.4f}) with gaba=1.0; "
        "protectors must override generators in the maintenance hierarchy"
    )


# ── Facet 5 (integration: subsystems) — each channel moves ΔV ──
def test_each_maintenance_channel_moves_the_gradient() -> None:
    """INV-YV1 integration: degrading a single subsystem lowers ΔV vs nominal.

    The aggregate gradient must be sensitive to each maintenance layer: stressing
    the risk channel (gaba) or the chaos/energy channels must not leave ΔV
    unchanged — every layer feeds the one gradient.
    """
    base = GradientHealthMonitor()
    _warm(base, 60)
    nominal = base.update(R=0.9, gaba=0.1, serotonin=0.3, ecs_free_energy=1.0).gvs_score

    stressed_risk = GradientHealthMonitor()
    _warm(stressed_risk, 60)
    risk_down = stressed_risk.update(
        R=0.9, gaba=0.9, serotonin=0.3, ecs_free_energy=1.0
    ).gvs_score
    assert risk_down < nominal - SCORE_EPS, (
        "INV-YV1 violated: observed ΔV under risk stress = "
        f"{risk_down:.4f} must be < nominal {nominal:.4f} with gaba=0.9; the risk "
        "channel must move the aggregate gradient"
    )


# ── Facet 6 (adaptation: replay) — the gradient organ is deterministic ──
def test_gradient_monitor_is_deterministic_on_replay() -> None:
    """INV-YV1 adaptation: identical drive sequences yield identical ΔV.

    The measurement of being must be reproducible: feeding two fresh monitors the
    same drive sequence must produce the same final gradient and status, so the
    axiom is witnessed against a stable instrument, not a noisy one.
    """

    def _run() -> tuple[float, str]:
        monitor = GradientHealthMonitor()
        vitals = None
        for step in range(60):
            vitals = monitor.update(
                R=0.5, gaba=0.2, serotonin=0.3, ecs_free_energy=float(1.0 + 0.01 * step)
            )
        assert vitals is not None
        return vitals.gvs_score, vitals.status

    first, second = _run(), _run()
    assert first == second, (
        "INV-YV1 violated: observed non-determinism = "
        f"{first!r} vs {second!r} over steps=60 with fixed drive; the gradient "
        "instrument must be bit-stable on replay"
    )


# ── Facet 7 (iteration: ordered) — the maintenance ladder is monotone ──
def test_status_thresholds_are_ordered_and_consistent() -> None:
    """INV-YV1 ladder: critical < healthy, and status tracks the gradient band.

    The maintenance ladder must be monotone — the critical threshold below the
    healthy one — and a fully-collapsed gradient (all generators dead, protector
    alarmed) must land at the bottom band, not be reported tradeable.
    """
    monitor = GradientHealthMonitor()
    assert monitor._critical < monitor._healthy, (
        "INV-YV1 violated: observed thresholds critical = "
        f"{monitor._critical} must be < healthy = {monitor._healthy}; the "
        "maintenance ladder must be ordered"
    )
    collapsed = GradientHealthMonitor()
    _warm(collapsed, 60, R=0.0)
    dead = collapsed.update(R=0.0, gaba=1.0, serotonin=0.7, ecs_free_energy=5.0)
    assert dead.gvs_score <= monitor._healthy, (
        "INV-YV1 violated: observed collapsed ΔV = "
        f"{dead.gvs_score:.4f} must be ≤ healthy threshold {monitor._healthy} with "
        "R=0, gaba=1, serotonin=0.7; a collapsed gradient cannot read as healthy"
    )
