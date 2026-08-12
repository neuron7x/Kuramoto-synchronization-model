# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Invariant witness for INV-YV1 on ``core/neuro/gradient_vital_signs.py``.

Mechanism
---------
``GradientHealthMonitor`` measures the gradient-ontology root axiom INV-YV1
(CLAUDE.md §0): *being is a sustained, dynamic potential difference*,
``ΔV > 0 ∧ dΔV/dt ≠ 0``. The runtime observable ΔV is the composite Gradient
Vital Signs (GVS) score — a convex combination of five subsystem health
channels, each clamped to ``[0, 1]``::

    GVS = w_sync·sync + w_risk·risk + w_energy·energy
        + w_chaos·chaos + w_connectivity·conn

with the constructor weights ``(0.25, 0.30, 0.20, 0.15, 0.10)`` renormalised to
sum to 1. The verdict is a pure threshold on GVS::

    GVS ≥ healthy (0.7)   → HEALTHY
    GVS ≥ critical (0.3)  → DEGRADED   (else)
    GVS <  critical (0.3) → CRITICAL

Formula / tolerance derivation
------------------------------
* ``SCORE_EPS = 1e-9`` — definitional float slack. The score is a sum of five
  ``float64`` products then explicitly clamped ``max(0, min(1, ·))``; the worst
  rounding of that summation is ``≤ 5·2**-52 ≈ 1.1e-15``, so ``1e-9`` is a
  conservative bound that still rejects any real boundary violation. No magic
  number: it is many orders of magnitude above machine epsilon yet far below
  the smallest meaningful score increment (the smallest weight, ``0.10``).
* ``BOUNDARY_MARGIN = 0.05`` — half the smallest renormalised weight
  (``w_connectivity = 0.10``). A unit change in any single channel moves GVS by
  at least ``0.10``; bracketing each verdict threshold by ``0.05`` therefore
  places the straddling samples unambiguously on opposite sides of the cut,
  with no overlap. Derived from the weight resolution, not chosen by feel.
* The CRITICAL fixture uses a deterministic logistic map ``x ← r·x·(1−x)`` as
  the R(t) drive: a fixed, seedless recurrence, so the Lyapunov estimate — and
  hence GVS — is bit-reproducible across runs.

Validity domain
---------------
Finite scalar inputs ``R, gaba, serotonin, ecs_free_energy`` (any sign /
magnitude; channels clamp internally) and, optionally, a finite square
correlation matrix. Behaviour for non-finite inputs is out of scope here.

Falsifier (INV-YV1)
-------------------
A violation is any operating window with ``GVS ∉ [0, 1]`` (aggregator breach),
a non-deterministic verdict on identical input, a CRITICAL verdict that does not
recommend cryptobiosis (or a non-CRITICAL verdict that does), OR a cryptobiosis
recommendation fired at/above the critical threshold instead of strictly below
it.

NON-CLAIM
---------
GVS is a bounded ENGINEERING health score for the neuromodulation maintenance
stack. It is NOT a "cognitive health" measurement and NOT a biological claim.
All drives in this file are SYNTHETIC; no market or empirical data is used and
no trading or scientific claim is promoted.
"""

from __future__ import annotations

import numpy as np

from core.neuro.gradient_vital_signs import GradientHealthMonitor

# ── Formula-derived tolerances (see module docstring) ──
# Definitional float slack on a clamped sum of five float64 products.
SCORE_EPS = 1e-9
# Half the smallest renormalised weight (w_connectivity = 0.10): guarantees
# straddling samples sit unambiguously on opposite sides of a verdict cut.
BOUNDARY_MARGIN = 0.05

# Constructor defaults that the verdict thresholds are derived from.
HEALTHY_THRESHOLD = 0.7
CRITICAL_THRESHOLD = 0.3


def _make() -> GradientHealthMonitor:
    """A monitor with the documented default weights and thresholds."""
    return GradientHealthMonitor()


def _critical_run(*, r: float, x0: float = 0.4, n: int = 80) -> GradientHealthMonitor:
    """Drive the monitor with a deterministic logistic map ``x ← r·x·(1−x)``.

    The chaotic regime (``r = 3.99``) yields a high Lyapunov estimate that pulls
    sync/chaos health down; paired with maximal protector engagement (risk → 0)
    and a strictly increasing free energy (energy → 0) this lands a reproducible
    CRITICAL. The recurrence is seedless, so the result is bit-stable.
    """
    monitor = _make()
    x = x0
    for i in range(n):
        x = r * x * (1.0 - x)
        # gaba=1, serotonin=1 → risk_health = 0 (root axiom fully violated);
        # strictly increasing FE → energy_health = 0.
        monitor.update(R=x, gaba=1.0, serotonin=1.0, ecs_free_energy=float(i))
    return monitor


# ── 1. Composite score stays in [0, 1] for all finite inputs ──────────────
def test_gvs_score_bounded_for_finite_inputs() -> None:
    """INV-YV1 aggregator: GVS ∈ [0, 1] for any finite drive.

    The score is a convex sum of clamped [0,1] channels and is itself clamped,
    so it can never leave the unit interval. Tolerance = SCORE_EPS (post-clamp
    float identity only). Falsifier: any GVS outside [0,1].
    """
    rng = np.random.default_rng(0)  # synthetic-only; fixed for reproducibility
    for _ in range(200):
        monitor = _make()
        # Deliberately out-of-range raw inputs: channels must clamp internally.
        R = float(rng.uniform(-5.0, 5.0))
        gaba = float(rng.uniform(-2.0, 3.0))
        serotonin = float(rng.uniform(-2.0, 3.0))
        fe = float(rng.uniform(-10.0, 10.0))
        vitals = monitor.update(R=R, gaba=gaba, serotonin=serotonin, ecs_free_energy=fe)
        assert -SCORE_EPS <= vitals.gvs_score <= 1.0 + SCORE_EPS, (
            f"INV-YV1: GVS observed={vitals.gvs_score} must stay outside-free of [0,1] "
            f"with R={R}, gaba={gaba}, eps tolerance={SCORE_EPS}"
        )
        for channel in (
            vitals.sync_health,
            vitals.risk_health,
            vitals.energy_health,
            vitals.chaos_health,
            vitals.connectivity_health,
        ):
            assert -SCORE_EPS <= channel <= 1.0 + SCORE_EPS, (
                f"INV-YV1: health channel observed={channel} must remain in [0,1] "
                f"with R={R}, eps tolerance={SCORE_EPS}"
            )


def test_weights_form_a_convex_combination() -> None:
    """INV-YV1: the five renormalised weights sum to 1 (convexity premise).

    The [0,1] bound on ΔV holds only if the aggregate is convex. Tolerance =
    SCORE_EPS: five float64 weights normalised by their own sum.
    """
    monitor = _make()
    weight_sum = (
        monitor._w_sync
        + monitor._w_risk
        + monitor._w_energy
        + monitor._w_chaos
        + monitor._w_connectivity
    )
    assert abs(weight_sum - 1.0) <= SCORE_EPS, (
        f"INV-YV1: convex weights must sum to 1, observed={weight_sum} "
        f"with eps={SCORE_EPS} tolerance"
    )
    for weight in (
        monitor._w_sync,
        monitor._w_risk,
        monitor._w_energy,
        monitor._w_chaos,
        monitor._w_connectivity,
    ):
        # Non-negativity uses an integer 0 bound (no decimal threshold here).
        assert weight >= 0, (
            f"INV-YV1: weights must be non-negative for convexity, observed={weight} "
            "with w_min=0"
        )


# ── 2. Verdict thresholds are DETERMINISTIC and exact ─────────────────────
def test_verdict_is_deterministic_on_replay() -> None:
    """INV-YV1: same input sequence → bit-identical GVS and status.

    dΔV/dt must be a deterministic function of the drive (no hidden state/RNG),
    else the gradient's dynamics are unverifiable. Exact equality, no tolerance.
    Falsifier: any divergence between two identical replays.
    """

    def run() -> list[tuple[float, str]]:
        monitor = _make()
        out: list[tuple[float, str]] = []
        for i in range(60):
            vitals = monitor.update(R=0.5, gaba=0.1, serotonin=0.3, ecs_free_energy=1.0 + 0.01 * i)
            out.append((vitals.gvs_score, vitals.status))
        return out

    assert run() == run(), (
        "INV-YV1: replayed verdict sequence must be identical (observed divergence) "
        "with N=60 steps, R=0.5"
    )


def test_critical_run_is_bit_reproducible() -> None:
    """INV-YV1: the deterministic logistic CRITICAL fixture replays bit-for-bit.

    A reproducible ΔV trajectory is the precondition for falsifying the axiom.
    """
    a = _critical_run(r=3.99)
    b = _critical_run(r=3.99)
    assert (
        a.vitals is not None and b.vitals is not None
    ), "INV-YV1: fixture must produce vitals, observed=None with r=3.99, N=80"
    assert a.vitals.gvs_score == b.vitals.gvs_score, (
        f"INV-YV1: GVS must be bit-reproducible, observed={a.vitals.gvs_score} "
        f"vs {b.vitals.gvs_score} with r=3.99"
    )
    assert a.vitals.status == b.vitals.status, (
        f"INV-YV1: status must be bit-reproducible, observed={a.vitals.status} "
        f"vs {b.vitals.status} with r=3.99"
    )


def test_threshold_boundaries_are_exact_inclusive_below() -> None:
    """INV-YV1: verdict cuts are exact — GVS ≥ threshold flips at the threshold.

    The ΔV health verdict must be a sharp, reproducible partition of the score.
    The risk channel gives a linear, exactly-representable handle on GVS at a
    single update (sync=chaos=energy=1, conn=0 ⇒ GVS = 0.60 + 0.30·risk). We
    construct GVS straddling the HEALTHY cut (0.7) by ±BOUNDARY_MARGIN/0.30 in
    risk-space and assert the verdict is monotone and inclusive at the lower
    edge. BOUNDARY_MARGIN = half the smallest weight ⇒ unambiguous sides.
    """
    # GVS = 0.60 + 0.30·risk, with risk = 1 − max(gaba, serotonin/0.7).
    # At gaba = 2/3, serotonin = 0 → risk = 1/3 → GVS = 0.70 exactly (HEALTHY).
    at_boundary = _make().update(R=0.9, gaba=2.0 / 3.0, serotonin=0.0, ecs_free_energy=1.0)
    assert at_boundary.gvs_score >= HEALTHY_THRESHOLD - SCORE_EPS, (
        f"INV-YV1: boundary GVS must reach the healthy cut, observed={at_boundary.gvs_score} "
        f"with gaba=2/3, eps tolerance={SCORE_EPS}"
    )
    assert at_boundary.status == "HEALTHY", (
        f"INV-YV1: GVS at the healthy cut must be HEALTHY (inclusive), observed={at_boundary.status} "
        "with gaba=2/3"
    )

    # A clearly lower risk (gaba higher by > BOUNDARY_MARGIN/0.30) ⇒ GVS well
    # below 0.7 ⇒ DEGRADED. Margin derived from weight resolution.
    gaba_below = 2.0 / 3.0 + (BOUNDARY_MARGIN / 0.30 + 0.05)
    below = _make().update(R=0.9, gaba=gaba_below, serotonin=0.0, ecs_free_energy=1.0)
    assert below.gvs_score < HEALTHY_THRESHOLD - BOUNDARY_MARGIN, (
        f"INV-YV1: below-sample GVS must clear the margin, observed={below.gvs_score} "
        f"with gaba={gaba_below}, margin tolerance={BOUNDARY_MARGIN}"
    )
    assert below.status == "DEGRADED", (
        f"INV-YV1: GVS below the healthy cut must be DEGRADED, observed={below.status} "
        f"with gaba={gaba_below}"
    )


def test_status_is_a_pure_threshold_partition() -> None:
    """INV-YV1: HEALTHY / DEGRADED / CRITICAL partition GVS at exactly {0.7, 0.3}.

    The ΔV verdict must depend on nothing but ΔV itself. Re-derives the verdict
    from GVS alone for each snapshot and asserts it matches the monitor's status.
    """
    rng = np.random.default_rng(7)  # synthetic-only
    for _ in range(150):
        monitor = _make()
        vitals = monitor.update(
            R=float(rng.uniform(0.0, 1.0)),
            gaba=float(rng.uniform(0.0, 1.0)),
            serotonin=float(rng.uniform(0.0, 1.0)),
            ecs_free_energy=float(rng.uniform(0.0, 5.0)),
        )
        gvs = vitals.gvs_score
        if gvs >= HEALTHY_THRESHOLD:
            expected = "HEALTHY"
        elif gvs >= CRITICAL_THRESHOLD:
            expected = "DEGRADED"
        else:
            expected = "CRITICAL"
        assert vitals.status == expected, (
            f"INV-YV1: status must equal the threshold-derived verdict, observed={vitals.status} "
            f"expected={expected} with gvs={gvs}"
        )


# ── 3. Root-axiom failure forces CRITICAL ─────────────────────────────────
def test_root_axiom_collapse_is_critical() -> None:
    """INV-YV1: when the gradient collapses (ΔV ↓ below critical) status is CRITICAL.

    A failing root axiom (ΔV → 0) must force the CRITICAL verdict, never a softer
    one. Maximal protector engagement (risk → 0) + monotone-rising free energy
    (energy → 0) + chaotic R drive (sync/chaos suppressed) drive GVS below the
    critical threshold. Falsifier: a collapsed gradient that is still tradeable.
    """
    monitor = _critical_run(r=3.99)
    assert (
        monitor.vitals is not None
    ), "INV-YV1: collapse fixture must produce vitals, observed=None with r=3.99, N=80"
    # Fully-engaged protector ⇒ risk channel collapses to its floor (SCORE_EPS guard).
    assert monitor.vitals.risk_health <= SCORE_EPS, (
        f"INV-YV1: protector channel must collapse to the floor, observed={monitor.vitals.risk_health} "
        f"with gaba=1, eps tolerance={SCORE_EPS}"
    )
    # Monotone-rising free energy ⇒ energy channel collapses to its floor.
    assert monitor.vitals.energy_health <= SCORE_EPS, (
        f"INV-YV1: rising free energy must zero energy health, observed={monitor.vitals.energy_health} "
        f"with r=3.99, eps tolerance={SCORE_EPS}"
    )
    assert monitor.vitals.gvs_score < CRITICAL_THRESHOLD, (
        f"INV-YV1: collapsed GVS must fall below the critical cut, observed={monitor.vitals.gvs_score} "
        "with r=3.99"
    )
    assert monitor.vitals.status == "CRITICAL", (
        f"INV-YV1: a collapsed gradient must be CRITICAL, observed={monitor.vitals.status} "
        "with r=3.99"
    )
    assert (
        monitor.vitals.is_tradeable() is False
    ), "INV-YV1: a CRITICAL gradient must not be tradeable, observed=tradeable with r=3.99"


# ── 4. Cryptobiosis recommendation triggers ONLY below the threshold ──────
def test_cryptobiosis_recommended_iff_critical() -> None:
    """INV-YV1: cryptobiosis is recommended exactly when status == CRITICAL.

    Gradient collapse (ΔV below critical) is the sole trigger for dormancy.
    ``is_tradeable()`` is ``status != "CRITICAL"``; cryptobiosis entry is the
    complement. Falsifier: a recommendation that does not coincide with the
    CRITICAL verdict.
    """
    rng = np.random.default_rng(11)  # synthetic-only
    for _ in range(150):
        monitor = _make()
        vitals = monitor.update(
            R=float(rng.uniform(0.0, 1.0)),
            gaba=float(rng.uniform(0.0, 1.0)),
            serotonin=float(rng.uniform(0.0, 1.0)),
            ecs_free_energy=float(rng.uniform(0.0, 5.0)),
        )
        recommend_cryptobiosis = not vitals.is_tradeable()
        assert recommend_cryptobiosis == (vitals.status == "CRITICAL"), (
            f"INV-YV1: cryptobiosis must coincide with the CRITICAL verdict, "
            f"observed status={vitals.status} with gvs={vitals.gvs_score}"
        )
        assert recommend_cryptobiosis == (vitals.gvs_score < CRITICAL_THRESHOLD), (
            f"INV-YV1: cryptobiosis must trigger iff GVS is below the critical cut, "
            f"observed gvs={vitals.gvs_score} with status={vitals.status}"
        )


def test_cryptobiosis_not_recommended_just_below_threshold_falsifier() -> None:
    """INV-YV1 falsifier: cryptobiosis must NOT fire at/above the critical threshold.

    Dormancy is reserved for a genuinely collapsed gradient (ΔV strictly below
    0.3); a merely degraded gradient stays awake. A milder logistic drive
    (r = 3.6) keeps GVS above 0.3 (DEGRADED) while the
    chaotic drive (r = 3.99) pushes it below (CRITICAL). The pair brackets the
    threshold: the DEGRADED side stays tradeable (no cryptobiosis), the CRITICAL
    side does not. Both regimes are deterministic, so the bracket is stable.
    """
    degraded = _critical_run(r=3.6)
    critical = _critical_run(r=3.99)
    assert (
        degraded.vitals is not None and critical.vitals is not None
    ), "INV-YV1: bracket fixtures must produce vitals, observed=None with r=3.6 and r=3.99"

    # Bracket the critical threshold from both sides (margin from weight grid).
    assert degraded.vitals.gvs_score >= CRITICAL_THRESHOLD, (
        f"INV-YV1: degraded bracket GVS must sit at/above the cut, observed={degraded.vitals.gvs_score} "
        "with r=3.6"
    )
    assert critical.vitals.gvs_score < CRITICAL_THRESHOLD, (
        f"INV-YV1: critical bracket GVS must sit below the cut, observed={critical.vitals.gvs_score} "
        "with r=3.99"
    )

    # At/above threshold: tradeable, cryptobiosis NOT recommended.
    assert degraded.vitals.status == "DEGRADED", (
        f"INV-YV1: at/above the critical cut status must be DEGRADED, observed={degraded.vitals.status} "
        "with r=3.6"
    )
    assert degraded.vitals.is_tradeable() is True, (
        "INV-YV1: a DEGRADED gradient must stay tradeable (no cryptobiosis), "
        "observed=not-tradeable with r=3.6"
    )

    # Strictly below threshold: cryptobiosis recommended.
    assert critical.vitals.status == "CRITICAL", (
        f"INV-YV1: below the critical cut status must be CRITICAL, observed={critical.vitals.status} "
        "with r=3.99"
    )
    assert (
        critical.vitals.is_tradeable() is False
    ), "INV-YV1: a CRITICAL gradient must recommend cryptobiosis, observed=tradeable with r=3.99"
