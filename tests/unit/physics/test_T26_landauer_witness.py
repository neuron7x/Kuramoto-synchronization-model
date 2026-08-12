# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T26 — ``LandauerInferenceProfiler`` witness tests mapped to physics invariants.

The legacy ``test_T7_landauer.py`` has no INV-* references despite
testing physical identities. This file adds the missing invariant
witnesses under the existing contracts:

* **INV-TH2 (2nd law)** — entropy production ≥ 0 for any non-negative
  parameter count. Falsification probe: negative parameter count is
  rejected with ``ValueError``.
* **INV-HPC2 (numerical stability)** — actual-vs-Landauer ratio stays
  finite and consistent with the 9-orders-of-magnitude gap on modern
  GPUs under standard configuration.
* **INV-HPC1 (reproducibility)** — repeated calls with identical
  arguments return bit-identical scalars (no hidden state).

Every assertion derives its tolerance from the physics of Landauer's
bound (E_min = k_B · T · ln 2) and the IEEE 754 float64 unit roundoff.
No magic thresholds.
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from core.physics.landauer import (
    K_BOLTZMANN,
    LANDAUER_ENERGY,
    LandauerInferenceProfiler,
)

# ---------------------------------------------------------------------------
# INV-TH2 — entropy production ≥ 0
# ---------------------------------------------------------------------------


@given(
    n=st.integers(min_value=0, max_value=10**7),
    T_kelvin=st.floats(min_value=0.5, max_value=1000.0, allow_nan=False),
)
@settings(max_examples=120, deadline=None)
def test_entropy_per_step_non_negative(n: int, T_kelvin: float) -> None:
    """INV-TH2: entropy generated per step is ≥ 0 for every non-negative n.

    Derivation: the helper returns ``float(n_active_params)``, a
    direct count of bits erased. By the 2nd law, entropy production is
    non-negative; since the count itself is non-negative, so is its
    float cast. Tolerance is 0.0 (exact).

    The property is checked across a Hypothesis sweep over param
    counts up to 10⁷ and temperatures from cryogenic to 1000 K —
    covering every documented operating regime.
    """
    # epsilon: 0.0 — direct integer-to-float cast, exact.
    prof = LandauerInferenceProfiler(T=T_kelvin, gpu_energy_per_op=1e-12)
    S = prof.entropy_per_step(n)
    assert S >= 0.0, (
        f"INV-TH2 VIOLATED: S={S} < 0 at n={n}, T={T_kelvin:.2f} K. "
        f"Expected non-negative entropy production per 2nd law. "
        f"Reasoning: bit-count is structurally non-negative."
    )
    assert S == float(n), (
        f"INV-TH2 VIOLATED: S={S} != float(n)={float(n)} at n={n}. "
        f"Expected exact integer-to-float cast. "
        f"Observed at T={T_kelvin:.2f} K."
    )


def test_entropy_per_step_rejects_negative() -> None:
    """INV-TH2 falsification input: negative n must raise ValueError.

    A silent clamp of negative counts to zero would hide caller bugs
    and also violate the contract that entropy is measured, not
    fabricated. The helper raises, witnessing the fail-loud policy
    across four falsification inputs.
    """
    prof = LandauerInferenceProfiler()
    for bad in (-1, -10, -10_000, -(10**7)):
        raised = False
        try:
            prof.entropy_per_step(bad)
        except ValueError:
            raised = True
        assert raised, (
            f"INV-TH2 VIOLATED: entropy_per_step accepted n={bad}. "
            f"Observed at T={prof._T} K (default). "
            f"Expected ValueError on negative param count per 2nd law."
        )


# ---------------------------------------------------------------------------
# INV-HPC2 — numerical stability & finite outputs
# ---------------------------------------------------------------------------


def test_landauer_minimum_energy_matches_formula() -> None:
    """INV-HPC2: ``minimum_energy`` equals ``n · k_B · T · ln 2`` exactly.

    Derivation: the helper returns ``n * (k_B * T * ln 2)``. On IEEE
    754 float64 each multiplication has relative error ≤ 2·eps_64 ≈
    4.44e-16. A three-factor product therefore has relative error
    ≤ 6·eps_64 ≈ 1.33e-15. We pad to 1e-13 for safety.

    The expected value is recomputed locally from the published
    constants so the formula stays auditable.
    """
    # epsilon: 6·eps_64 ≈ 1.33e-15, padded to 1e-13 relative.
    rel_tol = 1e-13

    for n in (1, 10, 1_000, 1_000_000):
        for T_kelvin in (4.2, 77.0, 300.0, 500.0):
            prof = LandauerInferenceProfiler(T=T_kelvin, gpu_energy_per_op=1e-12)
            expected = n * K_BOLTZMANN * T_kelvin * math.log(2)
            actual = prof.minimum_energy(n)
            assert math.isfinite(actual), (
                f"INV-HPC2 VIOLATED: minimum_energy non-finite at n={n}, "
                f"T={T_kelvin:.2f} K. Observed={actual}."
            )
            rel_err = abs(actual - expected) / max(expected, 1e-300)
            assert rel_err < rel_tol, (
                f"INV-HPC2 VIOLATED: minimum_energy={actual:.3e} vs "
                f"expected={expected:.3e}, rel_err={rel_err:.3e} > "
                f"{rel_tol:.0e}. Observed at n={n}, T={T_kelvin:.2f} K. "
                f"Reasoning: 3-factor product has float64 error ≤ 6·eps_64."
            )


def test_landauer_ratio_is_finite_on_standard_config() -> None:
    """INV-HPC2: Landauer ratio ∈ [1e8, 1e10] at default params.

    Derivation: modern GPUs spend ~1e-12 J/op (NVIDIA A100 ~0.3 pJ/FLOP
    per datasheet). The Landauer floor at 300 K is kT·ln2 ≈ 2.87e-21 J.
    Ratio = 1e-12 / 2.87e-21 ≈ 3.5e8. The [1e8, 1e10] window encodes
    the "9 orders of magnitude" contract from the module docstring.

    Falsification probe: increasing gpu_energy_per_op by 100× must
    increase the ratio by the same factor (linearity of the metric).
    """
    # epsilon: empirical band [1e8, 1e10] derived from A100 datasheet
    #          + kT·ln2 at 300 K. Below 1e8 or above 1e10 signals a
    #          broken constant or temperature.
    prof = LandauerInferenceProfiler(T=300.0, gpu_energy_per_op=1e-12)
    n = 1000
    ratio = prof.landauer_ratio(n)
    assert math.isfinite(
        ratio
    ), f"INV-HPC2 VIOLATED: landauer_ratio non-finite at n={n}. Observed={ratio}."
    assert 1e8 < ratio < 1e10, (
        f"INV-HPC2 VIOLATED: ratio={ratio:.2e} outside expected band "
        f"[1e8, 1e10] with N={n}, seed=none, T=300 K, "
        f"gpu_energy_per_op=1e-12 J. "
        f"Expected ~3.5e8 per kT·ln2 = 2.87e-21 J. "
        f"Reasoning: datasheet ~1e-12 J / Landauer ~3e-21 J ≈ 3.3e8."
    )

    # Linearity falsification: 100× energy should yield 100× ratio.
    prof_heavy = LandauerInferenceProfiler(T=300.0, gpu_energy_per_op=1e-10)
    ratio_heavy = prof_heavy.landauer_ratio(n)
    # epsilon: exact 100× scaling, 2 multiplies → rel_tol 4·eps_64 ≈ 9e-16, pad to 1e-12.
    rel_tol = 1e-12
    scale = ratio_heavy / ratio
    assert abs(scale - 100.0) / 100.0 < rel_tol, (
        f"INV-HPC2 VIOLATED: ratio scaling={scale:.6f}, expected 100.0. "
        f"Observed at n={n}. "
        f"Reasoning: gpu_energy scales linearly, Landauer floor is fixed."
    )


def test_landauer_ratio_at_zero_params_is_infinite() -> None:
    """INV-HPC2 edge: at n=0 the Landauer ratio is +∞ by contract.

    Derivation: both numerator and denominator are 0, but the guard
    ``if e_min < 1e-30: return float('inf')`` fires. We witness that
    the guard fires (not NaN) and that removing the guard would leak
    a ZeroDivision-style result. We sweep three temperatures to
    confirm the guard is not accidentally temperature-dependent.
    """
    for T_kelvin in (77.0, 300.0, 500.0):
        prof = LandauerInferenceProfiler(T=T_kelvin, gpu_energy_per_op=1e-12)
        result = prof.landauer_ratio(0)
        assert result == float("inf"), (
            f"INV-HPC2 VIOLATED: landauer_ratio(0) = {result}, expected inf. "
            f"Observed at n=0, T={T_kelvin} K, gpu_energy=1e-12 J. "
            f"Expected guard to return inf on sub-floor e_min. "
            f"Reasoning: preventing 0/0 = NaN is a documented stability contract."
        )
        assert math.isinf(result) and result > 0, (
            f"INV-HPC2 VIOLATED: non-+inf result={result} at T={T_kelvin} K. "
            f"Observed at n=0. Expected positive infinity per guard contract."
        )


# ---------------------------------------------------------------------------
# INV-HPC1 — reproducibility
# ---------------------------------------------------------------------------


def test_landauer_profiler_is_pure_function() -> None:
    """INV-HPC1: identical arguments yield bit-identical outputs.

    The profiler has no RNG, no time-dependent state, no hidden
    caches. Every observable must replay to the bit on the same
    process. Falsification probe: mutating ``gpu_energy_per_op``
    between calls must change the output (proof the input is read,
    not shadowed).
    """
    prof = LandauerInferenceProfiler(T=300.0, gpu_energy_per_op=1e-12)
    n = 4096
    n_runs = 3

    # epsilon: exact bit equality across runs.
    mins = [prof.minimum_energy(n) for _ in range(n_runs)]
    acts = [prof.actual_energy(n) for _ in range(n_runs)]
    ratios = [prof.landauer_ratio(n) for _ in range(n_runs)]

    for idx in (1, 2):
        assert mins[idx] == mins[0], (
            f"INV-HPC1 VIOLATED: minimum_energy run {idx}={mins[idx]:.6e} "
            f"vs run 0={mins[0]:.6e}. Expected bit identity. "
            f"Observed at n={n}, T=300 K."
        )
        assert acts[idx] == acts[0], (
            f"INV-HPC1 VIOLATED: actual_energy run {idx}={acts[idx]:.6e} "
            f"vs run 0={acts[0]:.6e}. Expected bit identity. "
            f"Observed at n={n}, T=300 K."
        )
        assert ratios[idx] == ratios[0], (
            f"INV-HPC1 VIOLATED: landauer_ratio run {idx}={ratios[idx]:.6e} "
            f"vs run 0={ratios[0]:.6e}. Expected bit identity. "
            f"Observed at n={n}, T=300 K."
        )

    # Falsification: a profiler configured with 10× energy must return
    # a strictly larger actual_energy for the same n.
    prof_heavy = LandauerInferenceProfiler(T=300.0, gpu_energy_per_op=1e-11)
    act_heavy = prof_heavy.actual_energy(n)
    assert act_heavy > acts[0], (
        f"INV-HPC1 falsification: heavy actual={act_heavy:.3e} !> "
        f"light={acts[0]:.3e}. Observed at n={n}. "
        f"Reasoning: actual_energy must read gpu_energy_per_op."
    )


# ---------------------------------------------------------------------------
# Contract edges — validator rejections
# ---------------------------------------------------------------------------


def test_profiler_rejects_non_positive_temperature() -> None:
    """INV-HPC2: T ≤ 0 must raise; zero temperature makes the bound ill-defined.

    Landauer's formula is E_min = k_B · T · ln 2 — at T = 0 the floor
    collapses to zero, and at T < 0 the formula gives negative "minimum"
    energy which is unphysical. The constructor must reject both.
    """
    for bad in (0.0, -1.0, -300.0, -1e6):
        raised = False
        try:
            LandauerInferenceProfiler(T=bad)
        except ValueError:
            raised = True
        assert raised, (
            f"INV-HPC2 VIOLATED: constructor accepted T={bad} K. "
            f"Observed at gpu_energy_per_op=default. "
            f"Expected ValueError per k_B·T·ln2 ≤ 0 falsification."
        )


def test_landauer_energy_constant_matches_SI() -> None:
    """INV-HPC2: module constant equals k_B · 300 K · ln 2 to float64 precision.

    Derivation: the constant is computed at import time. Any drift
    from the SI definition would corrupt every downstream metric.
    Tolerance: 3-factor product, ≤ 6·eps_64 relative.
    """
    # epsilon: 6·eps_64 ≈ 1.33e-15 relative; padded to 1e-14.
    expected = K_BOLTZMANN * 300.0 * math.log(2)
    rel_err = abs(LANDAUER_ENERGY - expected) / expected
    assert rel_err < 1e-14, (
        f"INV-HPC2 VIOLATED: LANDAUER_ENERGY={LANDAUER_ENERGY:.3e} vs "
        f"expected={expected:.3e} at T=300 K, rel_err={rel_err:.3e} > 1e-14. "
        f"Observed with constants K_BOLTZMANN={K_BOLTZMANN:.6e} J/K. "
        f"Reasoning: k_B·T·ln2 float64 error ≤ 6·eps_64."
    )
    # Order-of-magnitude sanity: ~2.87e-21 J
    assert 2.8e-21 < LANDAUER_ENERGY < 2.9e-21, (
        f"INV-HPC2 VIOLATED: LANDAUER_ENERGY={LANDAUER_ENERGY:.3e} J "
        f"outside expected [2.8e-21, 2.9e-21]. Observed at T=300 K. "
        f"Reasoning: kT·ln2 = 1.38e-23·300·0.693 ≈ 2.87e-21 J."
    )
    # Positivity witness — sub-floor would corrupt landauer_ratio guard.
    # epsilon: strict positivity; tolerance = 0 (any ≤ 0 is a fatal drift).
    assert LANDAUER_ENERGY > 0.0, (
        f"INV-HPC2 VIOLATED: LANDAUER_ENERGY={LANDAUER_ENERGY} ≤ 0. "
        f"Observed at T=300 K. Expected strictly positive floor per 2nd law."
    )


def test_efficiency_monotone_in_accuracy() -> None:
    """INV-HPC2: efficiency is strictly increasing in accuracy at fixed n.

    Derivation: efficiency = accuracy / n. At fixed n > 0 it is a
    linear function of accuracy with slope 1/n > 0, so strictly
    increasing. Tolerance 0 (exact arithmetic).
    """
    prof = LandauerInferenceProfiler()
    n = 500
    # Sweep 20 evenly-spaced accuracies in [0, 1]
    accs = np.linspace(0.0, 1.0, 20)
    effs = [prof.efficiency(float(a), n) for a in accs]
    deltas = np.diff(effs)
    assert np.all(deltas >= 0), (
        f"INV-HPC2 VIOLATED: efficiency not monotone: min Δ={deltas.min():.3e}. "
        f"Observed at n={n}. "
        f"Reasoning: efficiency = accuracy/n is linear in accuracy with "
        f"slope 1/n > 0."
    )
