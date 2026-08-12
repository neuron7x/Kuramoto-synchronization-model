# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Determinism / finiteness witness for the HPC-Neuro bridge.

Ledger id : hpc-kernels-determinism (OPERATIONAL, ADD_TEST, P1)
Source    : core/neuro/hpc_neuro_bridge.py
Covers    : INV-HPC1, INV-HPC2

Mechanism
---------
``HPCNeuroBridge.process_hpc_output`` is a *pure arithmetic* translator
from HPC Active-Inference outputs ``(pwpe, action, state_entropy)`` to
normalised neuromodulator signals, then publishes two of them on a
``NeuroSignalBus``:

    stress     = sigmoid(pwpe_scale * |pwpe|)        # serotonin slot ∈ (0, 1)
    confidence = 1 / (1 + state_entropy)             # dopamine-like   ∈ (0, 1]
    bus.hpc_pwpe       = max(0, |pwpe|)              # ∈ [0, ∞)
    bus.serotonin_level = clip(stress, 0, 1)         # ∈ [0, 1]

Formula
-------
``_sigmoid`` is the numerically-stable logistic
``1/(1+e^{-x})`` for x ≥ 0 and ``e^{x}/(1+e^{x})`` for x < 0; both
branches return values in the open interval (0, 1) for finite x.
``compute_adaptive_threshold`` returns ``np.quantile(history, q)`` (a
deterministic order statistic) or ``0.0`` for empty history.

Validity
--------
Input contract: finite pwpe, action ∈ ℤ, state_entropy ≥ 0, valid bus.
The module contains **no** RNG, no global state, no wall-clock read on
the returned dict, so identical inputs MUST yield byte-identical dicts
and byte-identical bus signal slots. ``snapshot().timestamp`` reads
``time.time()`` and is therefore intentionally EXCLUDED from equality.

Falsifier
---------
INV-HPC1: two calls with the same input producing bit-different output
          (dict or bus slot) ⇒ hidden randomness / state leak ⇒ FAIL.
INV-HPC2: any NaN/Inf in a normalised output on finite input, or an
          output escaping its declared range ⇒ FAIL.

Tolerances
----------
The bridge performs no stochastic operation: every output is a
deterministic function of its inputs computed by the *same* float64
instruction stream on every call. Re-running an identical computation
on the same machine reproduces the exact same IEEE-754 bits, so the
correct tolerance for the determinism invariant (INV-HPC1) is **exact
equality** (``==`` / ``math.isclose(rel=0, abs=0)`` is unnecessary —
plain ``==``). No ``atol``/``rtol`` is introduced for determinism.
Range/finiteness checks (INV-HPC2) are boundary comparisons on closed
analytic intervals and likewise need no epsilon.

NON-CLAIM
---------
This is an engineering signal bridge. The "serotonin", "dopamine" and
"arousal" labels are arithmetic analogs of neuromodulator dynamics, NOT
biological measurements or claims. All inputs here are synthetic-only.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import pytest

from core.neuro.hpc_neuro_bridge import HPCNeuroBridge, _sigmoid
from core.neuro.signal_bus import NeuroSignalBus

# Synthetic, deterministic input fixtures: (pwpe, action, state_entropy).
# Spread across sign of pwpe (sigmoid uses |pwpe|), zero, and large
# magnitudes that drive sigmoid into its saturated regime. No RNG.
_INPUTS: List[Tuple[float, int, float]] = [
    (0.0, 0, 0.0),
    (0.5, 1, 0.25),
    (-0.5, 2, 0.25),  # |pwpe| symmetry: must match the +0.5 stress exactly
    (1.234, 3, 1.5),
    (-9.87, 4, 3.0),
    (50.0, 5, 0.0),  # deep saturation: sigmoid → 1.0 but must stay finite
    (-50.0, 6, 100.0),
]


def _make_bridge() -> Tuple[HPCNeuroBridge, NeuroSignalBus]:
    """Construct a bridge over a fresh bus with the default pwpe_scale."""
    bus = NeuroSignalBus()
    return HPCNeuroBridge(bus), bus


# ── INV-HPC1: determinism (same input → byte-identical output) ──────────


@pytest.mark.parametrize("pwpe, action, entropy", _INPUTS)
def test_process_output_is_deterministic_same_bridge(
    pwpe: float, action: int, entropy: float
) -> None:
    """INV-HPC1: repeated calls on one bridge return identical dicts.

    Falsifier: any differing key/value ⇒ hidden state between calls.
    """
    bridge, _bus = _make_bridge()
    first = bridge.process_hpc_output(pwpe, action, entropy)
    second = bridge.process_hpc_output(pwpe, action, entropy)
    # Exact equality — no tolerance: identical float64 instruction stream.
    assert first == second


@pytest.mark.parametrize("pwpe, action, entropy", _INPUTS)
def test_process_output_is_deterministic_fresh_bridge(
    pwpe: float, action: int, entropy: float
) -> None:
    """INV-HPC1: two independently-constructed bridges agree bit-for-bit.

    This is the "no hidden randomness / no reseed" falsifier: a fresh
    object with no seeding must reproduce the prior result exactly.
    """
    bridge_a, _ = _make_bridge()
    bridge_b, _ = _make_bridge()
    out_a = bridge_a.process_hpc_output(pwpe, action, entropy)
    out_b = bridge_b.process_hpc_output(pwpe, action, entropy)
    assert out_a == out_b


def test_no_hidden_randomness_across_many_runs() -> None:
    """INV-HPC1: 100 unseeded repetitions never diverge.

    A single divergence in any of the 100 trials falsifies determinism.
    """
    reference = None
    for _ in range(100):
        bridge, _ = _make_bridge()
        out = bridge.process_hpc_output(1.234, 3, 1.5)
        if reference is None:
            reference = out
        else:
            assert out == reference


def test_pwpe_sign_symmetry_is_exact() -> None:
    """INV-HPC1: stress depends on |pwpe|, so ±x give identical stress.

    Exact equality is required because ``_sigmoid`` is fed the same
    ``abs(pwpe)`` argument for both signs — same bits in, same bits out.
    """
    bridge, _ = _make_bridge()
    pos = bridge.process_hpc_output(0.5, 1, 0.25)
    neg = bridge.process_hpc_output(-0.5, 1, 0.25)
    assert pos["stress"] == neg["stress"]
    assert pos["serotonin_level"] == neg["serotonin_level"]


# ── INV-HPC1: deterministic bus publication ─────────────────────────────


@pytest.mark.parametrize("pwpe, action, entropy", _INPUTS)
def test_bus_publication_is_deterministic(pwpe: float, action: int, entropy: float) -> None:
    """INV-HPC1: identical inputs publish identical bus slots.

    ``snapshot().timestamp`` reads wall-clock and is intentionally
    excluded; all neuromodulator slots must match exactly.
    """
    bridge_a, bus_a = _make_bridge()
    bridge_b, bus_b = _make_bridge()
    bridge_a.process_hpc_output(pwpe, action, entropy)
    bridge_b.process_hpc_output(pwpe, action, entropy)
    snap_a = bus_a.snapshot().to_dict()
    snap_b = bus_b.snapshot().to_dict()
    # Drop the wall-clock field (non-deterministic by construction).
    snap_a.pop("timestamp")
    snap_b.pop("timestamp")
    assert snap_a == snap_b


def test_bus_slots_match_returned_signals() -> None:
    """INV-HPC1: published slots equal the dict the call returned.

    ``serotonin_level`` (= stress) and ``hpc_pwpe`` (= |pwpe|) must be
    consistent between the return value and the bus snapshot.
    """
    bridge, bus = _make_bridge()
    out = bridge.process_hpc_output(-9.87, 4, 3.0)
    snap = bus.snapshot()
    assert snap.serotonin_level == out["serotonin_level"]
    assert snap.hpc_pwpe == abs(out["pwpe"])


# ── INV-HPC2: finiteness and declared normalized ranges ─────────────────


@pytest.mark.parametrize("pwpe, action, entropy", _INPUTS)
def test_outputs_finite_and_in_range(pwpe: float, action: int, entropy: float) -> None:
    """INV-HPC2: finite input → finite, in-range normalised outputs.

    Declared ranges (signal_bus.NeuroSignals docstring):
        stress / serotonin_level ∈ [0, 1]   (sigmoid image, clipped)
        confidence               ∈ (0, 1]   for state_entropy ≥ 0
        hpc_pwpe (bus)           ∈ [0, ∞)   = max(0, |pwpe|)
    Boundary comparisons on closed analytic intervals — no epsilon.
    """
    bridge, bus = _make_bridge()
    out = bridge.process_hpc_output(pwpe, action, entropy)

    for key in ("pwpe", "stress", "confidence", "serotonin_level"):
        assert math.isfinite(out[key]), f"{key} non-finite"

    # serotonin / stress ∈ [0, 1]
    assert 0.0 <= out["stress"] <= 1.0
    assert 0.0 <= out["serotonin_level"] <= 1.0
    # confidence = 1/(1+entropy), entropy ≥ 0 ⇒ confidence ∈ (0, 1]
    assert 0.0 < out["confidence"] <= 1.0
    # action passes through unchanged
    assert out["action"] == action

    snap = bus.snapshot()
    assert math.isfinite(snap.hpc_pwpe)
    assert snap.hpc_pwpe >= 0.0
    assert 0.0 <= snap.serotonin_level <= 1.0


def test_sigmoid_saturation_stays_finite_and_bounded() -> None:
    """INV-HPC2: extreme magnitudes saturate sigmoid without NaN/Inf.

    The stable two-branch logistic must return a finite value in [0, 1]
    even at |x| = 1e3 where ``exp`` would overflow if used naively.
    """
    for x in (-1e3, -1e2, 0.0, 1e2, 1e3):
        y = _sigmoid(x)
        assert math.isfinite(y)
        assert 0.0 <= y <= 1.0
    # Monotone limits: large negative → 0, large positive → 1 (exact bits).
    assert _sigmoid(-1e3) == 0.0
    assert _sigmoid(1e3) == 1.0


# ── INV-HPC1: adaptive threshold determinism ────────────────────────────


def test_adaptive_threshold_deterministic_and_finite() -> None:
    """INV-HPC1 + INV-HPC2: quantile threshold is exact and finite.

    ``np.quantile`` is a deterministic order statistic; repeated calls
    on the same history must return the identical float, and the empty
    history must return exactly 0.0.
    """
    bridge, _ = _make_bridge()
    history = [0.1, 0.4, 0.2, 0.9, 0.05, 0.6]
    t1 = bridge.compute_adaptive_threshold(history, quantile=0.9)
    t2 = bridge.compute_adaptive_threshold(history, quantile=0.9)
    assert t1 == t2  # exact: same numpy reduction, same bits
    assert math.isfinite(t1)
    # threshold lies within the data range it summarises
    assert min(history) <= t1 <= max(history)
    # empty history → exactly 0.0 (documented sentinel)
    assert bridge.compute_adaptive_threshold([], quantile=0.9) == 0.0
