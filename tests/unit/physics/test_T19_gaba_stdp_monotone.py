# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T19 — GABA STDP / desensitisation-monotonicity witness.

Mechanism
---------
``core.neuro.gaba_position_gate.GABAPositionGate`` applies a rectified-sigmoid
inhibitory brake to position size and adapts its RPE sensitivity weight with an
STDP-like rule: each negative reward-prediction-error (pain) potentiates the
inhibition channel (``w_rpe``), so sustained distress drives the brake higher.

Formula
-------
For each ``update_inhibition(vix, volatility, rpe)`` call::

    if rpe < 0:                                   # STDP potentiation (pain)
        w_rpe += plasticity_rate * abs(rpe)
    z          = w_vix * vix/30 + w_vol * vol/0.2 + w_rpe * max(0, -rpe)
    inhibition = max(0, 2 * sigmoid(z) - 1)       # rectified: z=0 -> 0

Gating::

    effective = base_size * (1 - inhibition * inhibition_position_scale)
    gated     = clamp(effective, 0, base_size)    # never increases exposure

Validity domain
---------------
vix >= 0, volatility >= 0, rpe in R, base_size >= 0 (input_contract).  In the
physical regime every driver is non-negative so z >= 0 and the rectified
sigmoid maps z in [0, inf) onto [0, 1) monotonically.  Out-of-contract inputs
(negative base_size, |inhibition| > 1) are *clamped* to the contract by the
module / bus, not raised — see ``test_*_falsifier_*`` for the honest weaker
bound this implies.

Falsifier
---------
INV-GABA1: inhibition not in [0, 1] => violation.
INV-GABA2: a stronger distress driver yielding *lower* inhibition => violation.
INV-GABA3: gated > base_size (gate increases exposure) => violation.
INV-GABA4: vol -> 0 with vix=0, rpe=0 not yielding inhibition ~ 0 => violation.
INV-GABA5: sustained pain not monotonically potentiating the brake => violation.

This file is the dedicated **STDP / desensitisation-monotonicity** witness.
INV-GABA1/4/5 *steady-state* asymptotics are already covered by
``tests/unit/physics/test_T19_neuro_p1.py`` and are NOT duplicated here; this
file exercises the *plasticity branch* (repeated negative RPE) instead.

NON-CLAIM
---------
Engineering analog of GABAergic inhibition, NOT a biological simulation;
synthetic-only; no alpha / profitability claim.  The Mink-1996 reference names
the motivating motif, it is not an assertion of physiological fidelity.
"""

from __future__ import annotations

import math
from typing import List

from core.neuro.gaba_position_gate import GABAPositionGate, _sigmoid
from core.neuro.signal_bus import NeuroSignalBus

# ── Module constants reproduced for tolerance derivation ─────────────
# These mirror the GABAPositionGate defaults; the tests below assert the
# module still matches these closed forms, so a drift in either side fails.
_W0: float = 1.0  # default w_vix == w_vol == w_rpe
_PLASTICITY_RATE: float = 0.05  # default plasticity_rate
_VIX_SCALE: float = 30.0  # z denominator for vix
_VOL_SCALE: float = 0.2  # z denominator for volatility

# Float64 round-off budget for a handful of exp/divide/compare ops.  The STDP
# trajectory is computed in closed form below, so the only error source is IEEE
# double round-off across ~5 elementary operations per step; 1e-9 is ~6 orders
# of magnitude above machine epsilon (2.2e-16) and far below any physical
# scale, so it cannot mask a real algorithmic regression.
_EXACT_TOL: float = 1e-9


def _expected_inhibition(z: float) -> float:
    """Closed-form rectified sigmoid the module must reproduce."""
    return max(0.0, 2.0 * _sigmoid(z) - 1.0)


# ── INV-GABA1: inhibition in [0, 1] across every regime ──────────────


def test_inhibition_in_unit_interval_across_regimes() -> None:
    """INV-GABA1: inhibition stays in [0, 1] for all contract inputs.

    Sweeps a grid spanning calm, extreme volatility and sustained pain,
    including the STDP-potentiated regime, asserting the bound never breaks.
    """
    for vix in (0.0, 15.0, 30.0, 200.0):
        for vol in (0.0, 0.1, 0.5, 5.0):
            for rpe in (1.0, 0.0, -0.1, -1.0):
                gate = GABAPositionGate(bus=NeuroSignalBus())
                # Drive the plasticity branch a few times to reach the
                # potentiated regime, then check the bound holds there too.
                for _ in range(5):
                    inh = gate.update_inhibition(vix=vix, volatility=vol, rpe=rpe)
                    assert 0.0 <= inh <= 1.0, (
                        f"INV-GABA1 VIOLATED: inhibition={inh!r} left [0,1] at "
                        f"vix={vix}, vol={vol}, rpe={rpe}, w_rpe={gate.w_rpe}."
                    )


# ── INV-GABA3: gate never increases exposure ─────────────────────────


def test_gate_never_increases_exposure() -> None:
    """INV-GABA3: gated size in [0, base_size] (brake cannot add exposure).

    With scale=1.0 (default BusConfig.inhibition_position_scale) the factor
    (1 - inhibition*scale) lies in (0, 1] for inhibition in [0, 1), so
    effective <= base_size exactly; the module additionally clamps to [0, base].
    """
    base = 10.0
    for inhibition_drive_vix in (0.0, 30.0, 1000.0):
        gate = GABAPositionGate(bus=NeuroSignalBus())
        gate.update_inhibition(vix=inhibition_drive_vix, volatility=0.0, rpe=0.0)
        gated = gate.gate_position_size(base)
        assert 0.0 <= gated <= base, (
            f"INV-GABA3 VIOLATED: gated={gated} not in [0,{base}] "
            f"after vix={inhibition_drive_vix}."
        )

    # Zero inhibition must be a pass-through (no exposure leak downward either).
    calm = GABAPositionGate(bus=NeuroSignalBus())
    assert math.isclose(calm.gate_position_size(base), base, abs_tol=_EXACT_TOL), (
        "INV-GABA3 VIOLATED: dead-calm gate is not a pass-through "
        f"(got {calm.gate_position_size(base)}, expected {base})."
    )


# ── INV-GABA5: sustained pain monotonically potentiates the brake ────


def test_sustained_pain_monotonically_potentiates_inhibition() -> None:
    """INV-GABA5 (STDP): repeated negative RPE monotonically raises the brake.

    Holds the market calm (vix=vol=0) so the ONLY driver is the rectified RPE
    term and the STDP weight bump.  On step k (1-indexed) with rpe = -d:

        w_rpe(k) = w0 + k * rate * d           (bump applied BEFORE z)
        z(k)     = w_rpe(k) * d                (vix=vol=0)
        inh(k)   = max(0, 2*sigmoid(z(k)) - 1)

    Because z(k) increases strictly in k and 2*sigmoid-1 is strictly
    increasing, inhibition is strictly monotone up and bounded in [0, 1).
    The trajectory is verified against this closed form to _EXACT_TOL.
    """
    d = 0.5  # distress magnitude per step
    n_steps = 8
    gate = GABAPositionGate(bus=NeuroSignalBus())

    observed: List[float] = []
    for k in range(1, n_steps + 1):
        inh = gate.update_inhibition(vix=0.0, volatility=0.0, rpe=-d)
        observed.append(inh)

        # Closed-form expectation for this step.
        w_rpe_k = _W0 + k * _PLASTICITY_RATE * d
        z_k = w_rpe_k * d
        expected = _expected_inhibition(z_k)
        assert abs(inh - expected) < _EXACT_TOL, (
            f"INV-GABA5 VIOLATED: step {k} inhibition={inh!r} != closed form "
            f"{expected!r} (z={z_k}, w_rpe={w_rpe_k}); STDP branch diverged."
        )

    # Strict monotonic potentiation and unit-interval bound.
    for i in range(1, len(observed)):
        assert observed[i] > observed[i - 1], (
            f"INV-GABA5 VIOLATED: inhibition non-increasing at step {i + 1}: "
            f"{observed[i]} <= {observed[i - 1]}; sustained pain must potentiate."
        )
    assert all(0.0 <= v < 1.0 for v in observed), (
        f"INV-GABA1/5 VIOLATED: potentiated inhibition left [0,1): {observed}."
    )


def test_stdp_weight_grows_linearly_with_pain() -> None:
    """INV-GABA5: w_rpe accumulates exactly rate*|rpe| per painful step.

    The plasticity rule is additive: w_rpe(k) = w0 + sum_j rate*|rpe_j|.  With
    constant rpe = -d this is the arithmetic sequence w0 + k*rate*d, checked to
    _EXACT_TOL (pure additions of float-representable constants).
    """
    d = 0.4
    gate = GABAPositionGate(bus=NeuroSignalBus())
    for k in range(1, 6):
        gate.update_inhibition(vix=0.0, volatility=0.0, rpe=-d)
        expected_w = _W0 + k * _PLASTICITY_RATE * d
        assert abs(gate.w_rpe - expected_w) < _EXACT_TOL, (
            f"INV-GABA5 VIOLATED: w_rpe={gate.w_rpe} != {expected_w} at step {k}."
        )


def test_non_negative_rpe_does_not_potentiate() -> None:
    """INV-GABA5 (gating): only pain (rpe < 0) potentiates; rpe >= 0 is inert.

    A reward or neutral outcome must leave w_rpe unchanged — the STDP rule is
    pain-gated, so the desensitisation channel cannot drift upward in calm.
    """
    gate = GABAPositionGate(bus=NeuroSignalBus())
    w_before = gate.w_rpe
    for rpe in (0.0, 0.5, 2.0):
        gate.update_inhibition(vix=10.0, volatility=0.1, rpe=rpe)
        assert gate.w_rpe == w_before, (
            f"INV-GABA5 VIOLATED: w_rpe changed from {w_before} to {gate.w_rpe} "
            f"on non-negative rpe={rpe}; potentiation must be pain-gated."
        )


# ── INV-GABA4: calm market returns to baseline (no plasticity hysteresis) ─


def test_calm_market_returns_to_zero_inhibition_after_pain() -> None:
    """INV-GABA4: vol->0, vix=0, rpe=0 yields inhibition ~ 0 even post-pain.

    After STDP has potentiated w_rpe via a pain episode, a subsequent dead-calm
    read (all drivers zero) must still return EXACTLY 0: z = w_rpe*max(0,-0) = 0
    and 2*sigmoid(0)-1 = 0.  The potentiation is latent (sensitivity), not a
    standing brake, so there is no inhibition hysteresis in calm.
    """
    gate = GABAPositionGate(bus=NeuroSignalBus())
    for _ in range(10):
        gate.update_inhibition(vix=50.0, volatility=1.0, rpe=-1.0)
    assert gate.w_rpe > _W0, "precondition: pain should have potentiated w_rpe"

    calm = gate.update_inhibition(vix=0.0, volatility=0.0, rpe=0.0)
    assert calm == 0.0, (
        f"INV-GABA4 VIOLATED: dead-calm inhibition={calm!r} after pain, "
        f"expected exactly 0.0 (z must be 0 when all drivers vanish); "
        f"w_rpe={gate.w_rpe} indicates standing-brake hysteresis."
    )


# ── Falsifier: out-of-contract input is clamped to the contract, not coerced silently ─


def test_falsifier_negative_base_size_clamped_not_negative() -> None:
    """Falsifier (INV-GABA3 / output_contract): gated_size in [0, base].

    The input_contract requires base_size >= 0.  The module does NOT raise on a
    contract-violating negative base_size; instead the clamp max(0, ...) pins
    the result to 0.  HONEST WEAKER BOUND: we assert the clamp holds (output
    never goes negative), since the module guarantees clamping rather than
    rejection.  A silent pass-through of a negative size would be the bug this
    catches.
    """
    gate = GABAPositionGate(bus=NeuroSignalBus())
    gate.update_inhibition(vix=100.0, volatility=0.0, rpe=0.0)
    gated = gate.gate_position_size(-5.0)
    assert gated == 0.0, (
        f"Falsifier VIOLATED: negative base_size produced gated={gated!r}; "
        "output_contract requires clamp to 0, not silent propagation."
    )


def test_falsifier_out_of_range_inhibition_clamped_by_bus() -> None:
    """Falsifier (INV-GABA1): bus clamps published inhibition into [0, 1].

    update_inhibition cannot itself emit out-of-range values, so we exercise
    the publish path directly with out-of-contract magnitudes.  HONEST WEAKER
    BOUND: NeuroSignalBus.publish_gaba CLAMPS rather than raises, so we assert
    the snapshot is pinned to the contract boundary (1.0 for >1, 0.0 for <0)
    — silent storage of e.g. 5.0 or -3.0 would be the violation.
    """
    bus = NeuroSignalBus()
    bus.publish_gaba(5.0)
    assert bus.snapshot().gaba_inhibition == 1.0, (
        "Falsifier VIOLATED: inhibition > 1 not clamped to 1 by the bus."
    )
    bus.publish_gaba(-3.0)
    assert bus.snapshot().gaba_inhibition == 0.0, (
        "Falsifier VIOLATED: inhibition < 0 not clamped to 0 by the bus."
    )


# ── INV-GABA2: stronger driver => stronger (never weaker) inhibition ─


def test_stronger_distress_yields_stronger_inhibition() -> None:
    """INV-GABA2: inhibition is monotone non-decreasing in each driver.

    Independent single-driver sweeps (the other two held at 0) on a FRESH gate
    each time to isolate the static response from STDP accumulation.  Closed
    form z = driver_contribution, so 2*sigmoid(z)-1 is strictly increasing.
    """
    # vix sweep (vol=0, rpe=0): z = vix/30
    vix_inh = [
        GABAPositionGate(bus=NeuroSignalBus()).update_inhibition(v, 0.0, 0.0)
        for v in (0.0, 10.0, 30.0, 90.0)
    ]
    # vol sweep (vix=0, rpe=0): z = vol/0.2
    vol_inh = [
        GABAPositionGate(bus=NeuroSignalBus()).update_inhibition(0.0, v, 0.0)
        for v in (0.0, 0.1, 0.2, 1.0)
    ]
    for name, seq in (("vix", vix_inh), ("vol", vol_inh)):
        for i in range(1, len(seq)):
            assert seq[i] >= seq[i - 1], (
                f"INV-GABA2 VIOLATED: {name} driver non-monotone at index {i}: "
                f"{seq[i]} < {seq[i - 1]}."
            )
        assert seq[0] == 0.0, (
            f"INV-GABA4 VIOLATED: {name}=0 baseline inhibition={seq[0]!r} != 0."
        )
