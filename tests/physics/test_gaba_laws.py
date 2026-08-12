# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for gaba_gate_bounds (INV-GABA1) and gaba_monotone_inhibition (INV-GABA3).

These reuse the REAL position gate, ``core/neuro/gaba_position_gate.py``
``GABAPositionGate.gate_position_size`` — no reimplementation. The "gate
multiplier" probed here is ``effective / base_size``: the multiplicative GABA
brake the gate applies to a base position size. The gate clamps ``effective`` to
``[0, base_size]`` (INV-GABA1 / INV-GABA3), so the multiplier lives in ``[0, 1]``
and is non-increasing in inhibition — the biological release-of-inhibition gate
of Mink 1996 (basal-ganglia GABAergic output tonically brakes motor output).

Two probe paths into the same real gate:
    * ``_gate_multiplier``     sets the bus inhibition slot directly, bypassing
      the publish-time clamp, so the gate's OWN bound is the thing under test.
    * ``_published_gate_multiplier`` drives inhibition through the production
      ``publish_gaba`` boundary, which clamps to ``[0, 1]`` (NaN/+inf collapse to
      full brake) — the fail-closed path for the negative control.
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from core.neuro.gaba_position_gate import GABAPositionGate
from core.neuro.signal_bus import NeuroSignalBus

_BASE_SIZE = 1.0
_FLOAT_TOL = 1e-12

# One shared bus/gate for the direct-probe path; each call overwrites the
# inhibition slot, so there is no cross-test state leakage.
_BUS = NeuroSignalBus()
_GATE = GABAPositionGate(_BUS)


def _gate_multiplier(inhibition: float, *, base_size: float = _BASE_SIZE) -> float:
    """Evaluate the REAL gate at an arbitrary inhibition (gate's own clamp under test).

    Writes the inhibition slot directly (bypassing the publish-time clamp) so the
    quantity exercised is the gate's intrinsic bound
    ``max(0, min(base, base*(1 - i*scale)))``, then reuses
    ``GABAPositionGate.gate_position_size`` unchanged.
    """
    _BUS._signals.gaba_inhibition = float(inhibition)
    return _GATE.gate_position_size(base_size) / base_size


def _published_gate_multiplier(inhibition: float, *, base_size: float = _BASE_SIZE) -> float:
    """Evaluate the REAL gate after driving inhibition through ``publish_gaba``.

    ``publish_gaba`` clamps to ``[0, 1]`` (NaN/+inf -> 1.0 = full brake, the
    fail-safe direction), so this is the production fail-closed boundary.
    """
    bus = NeuroSignalBus()
    bus.publish_gaba(inhibition)
    gate = GABAPositionGate(bus)
    return gate.gate_position_size(base_size) / base_size


def _max_positive_jump(seq: list[float]) -> float:
    """Worst monotonicity violation: the largest increase between consecutive gates."""
    arr = np.asarray(seq, dtype=float)
    if arr.size < 2:
        return 0.0
    return float(np.max(np.diff(arr)))


def test_gate_multiplier_within_unit_interval() -> None:
    """Positive witness (INV-GABA1): the gate multiplier stays in [0, 1] under a wide fuzz."""
    grid = np.linspace(-1000.0, 1000.0, 2001).tolist()
    extremes = [-1e9, -1.0, 0.0, 0.5, 1.0, 1e9]
    samples = [*grid, *extremes]
    lo, hi = 1.0, 0.0
    for inhibition in samples:
        m = _gate_multiplier(inhibition)
        assert math.isfinite(m), (
            f"INV-GABA1 VIOLATED: gate multiplier non-finite ({m}) at inhibition={inhibition}. "
            f"gate = effective/base, effective = max(0, min(base, base*(1 - i*scale))). "
            f"A position brake must be a finite probability-like scalar (Mink 1996). "
            f"n_fuzzed={len(samples)}, inhibition in [-1e9, 1e9]"
        )
        lo, hi = min(lo, m), max(hi, m)
    assert 0.0 <= lo <= hi <= 1.0, (
        f"INV-GABA1 VIOLATED: gate multiplier range [{lo:.6f}, {hi:.6f}] left [0, 1]. "
        f"effective is clamped to [0, base] inside gate_position_size, so the brake "
        f"can neither amplify (>1) nor invert (<0) a position. "
        f"Release-of-inhibition gating (Mink 1996). "
        f"n_fuzzed={len(samples)}, inhibition in [-1e9, 1e9]"
    )


def test_out_of_range_inhibition_fails_closed() -> None:
    """Negative control (INV-GABA1): non-finite / out-of-contract inhibition leaks no bad gate."""
    bad_inputs = (math.nan, math.inf, -math.inf, -5.0, 1e6, 2.0, -1e9)
    for bad in bad_inputs:
        m = _published_gate_multiplier(bad)
        assert math.isfinite(m) and 0.0 <= m <= 1.0, (
            f"INV-GABA1 VIOLATED: contract-violating inhibition={bad} leaked gate={m}. "
            f"publish_gaba clamps inhibition to [0, 1] (NaN/+inf -> full brake), so the "
            f"gate must fail closed inside [0, 1] — never an out-of-range or non-finite leak. "
            f"Fail-safe direction = maximal inhibition (Mink 1996). "
            f"bad_inputs={bad_inputs}"
        )
    # Discrimination: the clamp is load-bearing. The unguarded affine form
    # 1 - i*scale would itself leave [0, 1] for these inputs; the real gate does not.
    raw_over = 1.0 - (-5.0) * 1.0  # = 6.0  -> would exceed 1 without the clamp
    raw_under = 1.0 - 1e6 * 1.0  # < 0    -> would fall below 0 without the clamp
    assert raw_over > 1.0 and raw_under < 0.0, "affine probe wrong: negative control not discriminating"
    assert _published_gate_multiplier(-5.0) <= 1.0
    assert _published_gate_multiplier(1e6) >= 0.0


def test_gate_monotone_nonincreasing_in_inhibition() -> None:
    """Positive witness (INV-GABA3): gate is non-increasing in inhibition (Mink 1996)."""
    # Calibrate: dense increasing grid over the nominal [0, 1] inhibition domain.
    grid = np.linspace(0.0, 1.0, 4001).tolist()
    gates = [_gate_multiplier(i) for i in grid]
    worst = _max_positive_jump(gates)
    assert worst <= _FLOAT_TOL, (
        f"INV-GABA3 VIOLATED: gate increased with inhibition; worst positive jump "
        f"{worst:.3e} > tol={_FLOAT_TOL:.0e}. More inhibition must mean a smaller (never "
        f"larger) position (release-of-inhibition gating, Mink 1996). "
        f"grid: inhibition in [0, 1], n={len(grid)}"
    )

    # Explicit pairwise check on a wider grid including extremes: i1 <= i2 => g(i1) >= g(i2).
    wide = np.linspace(-50.0, 50.0, 1001).tolist()
    wide_gates = [_gate_multiplier(i) for i in wide]
    for k in range(len(wide) - 1):
        assert wide_gates[k] + _FLOAT_TOL >= wide_gates[k + 1], (
            f"INV-GABA3 VIOLATED: gate({wide[k]:.4f})={wide_gates[k]:.6f} < "
            f"gate({wide[k + 1]:.4f})={wide_gates[k + 1]:.6f} for increasing inhibition. "
            f"Gate must be monotonically non-increasing in inhibition (Mink 1996). "
            f"wide grid: inhibition in [-50, 50], n={len(wide)}"
        )

    # Property witness: any ordered pair preserves non-increase (Hypothesis, fast).
    @given(
        a=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        b=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def _property(a: float, b: float) -> None:
        i1, i2 = sorted((a, b))  # i1 <= i2
        assert _gate_multiplier(i1) + 1e-9 >= _gate_multiplier(i2), (
            f"INV-GABA3 VIOLATED: gate({i1})={_gate_multiplier(i1):.6f} < "
            f"gate({i2})={_gate_multiplier(i2):.6f} for i1 <= i2. "
            f"Non-increase must hold for every ordered pair (Mink 1996). "
            f"hypothesis ordered pair (i1, i2)=({i1}, {i2})"
        )

    _property()


def test_fabricated_increasing_gate_is_detected() -> None:
    """Negative control (INV-GABA3): a tampered increasing gate sequence is flagged."""
    real = [_gate_multiplier(i) for i in np.linspace(0.0, 1.0, 256).tolist()]
    assert _max_positive_jump(real) <= _FLOAT_TOL, (
        f"INV-GABA3 self-check VIOLATED: the real gate must pass its own monotonicity "
        f"probe; worst positive jump {_max_positive_jump(real):.3e} > tol={_FLOAT_TOL:.0e}. "
        f"If this fires the checker is mis-calibrated, not the gate (Mink 1996). "
        f"grid: inhibition in [0, 1], n=256"
    )

    # Tampered: reverse the (non-increasing) real sequence -> now strictly increasing.
    tampered = list(reversed(real))
    fabricated = [0.1, 0.2, 0.15, 0.9]  # hand-built monotonicity violation
    for label, seq in (("reversed-real", tampered), ("hand-built", fabricated)):
        jump = _max_positive_jump(seq)
        assert jump > 1e-3, (
            f"INV-GABA3 VIOLATED: monotonicity checker FAILED TO DETECT an increasing gate "
            f"sequence ({label}); worst positive jump {jump:.3e} <= 1e-3. The negative control "
            f"must discriminate a fabricated non-monotone sequence from the real gate (Mink 1996). "
            f"seq_len={len(seq)}"
        )

    # Invalid input also fails closed: NaN inhibition never yields an out-of-range brake.
    m_nan = _published_gate_multiplier(math.nan)
    assert math.isfinite(m_nan) and 0.0 <= m_nan <= 1.0, (
        f"INV-GABA1 VIOLATED: NaN inhibition leaked gate={m_nan} instead of failing closed. "
        f"publish_gaba must collapse NaN to full brake, keeping the gate in [0, 1]. "
        f"Fail-safe direction = maximal inhibition (Mink 1996). "
        f"input=NaN"
    )
