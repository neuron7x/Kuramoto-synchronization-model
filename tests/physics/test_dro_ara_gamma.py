# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for dro_ara_gamma_derivation (INV-DRO1 / INV-DRO5).

Executable falsification contract for the DRO-ARA scaling law

    gamma = 2 * H + 1            (Peng et al. 1994, DFA)

where ``H`` is the DFA-1 Hurst exponent estimated on the log-returns of a
price series. The defining property of the law is that ``gamma`` is *derived*
from ``H`` and is NEVER assigned independently: the real estimator
:func:`core.dro_ara.engine.derive_gamma` is the only admissible source of
``gamma``, and any value that does not satisfy ``|gamma - (2H+1)| < 1e-5`` is a
contract violation.

This file binds:

* a POSITIVE witness — the real ``derive_gamma`` output satisfies the
  algebraic identity across a seeded sweep of inputs; and
* a NEGATIVE control — an independently-assigned ``gamma`` that differs from
  ``2H+1`` is rejected by the same predicate (it cannot be smuggled past the
  invariant), AND degenerate inputs fail closed with ``ValueError`` (INV-DRO5).

The estimator (``derive_gamma`` and the DFA Hurst it wraps) is REUSED, never
reimplemented — the whole point is to falsify the real code path.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from core.dro_ara.engine import derive_gamma

# Documented tolerance of INV-DRO1: |gamma - (2H+1)| < 1e-5.
_GAMMA_H_TOL: float = 1e-5

# Seeds used for the positive sweep; each yields a distinct measured H.
_POSITIVE_SEEDS: tuple[int, ...] = (0, 1, 7, 42, 101, 2024)


def _gamma_consistent_with_hurst(gamma: float, hurst: float) -> bool:
    """Return True iff ``gamma`` satisfies the derivation law to spec tolerance.

    This is the SINGLE predicate that defines the law. The positive witness
    feeds it the real estimator output (must be True); the negative control
    feeds it an independently-assigned ``gamma`` (must be False). Sharing the
    predicate is what makes the negative control discriminating rather than
    vacuous.
    """
    return abs(gamma - (2.0 * hurst + 1.0)) < _GAMMA_H_TOL


def _seeded_random_walk(seed: int, n: int = 1024) -> NDArray[np.float64]:
    """Deterministic random-walk price proxy for a given seed."""
    rng = np.random.default_rng(seed=seed)
    walk: NDArray[np.float64] = np.cumsum(rng.normal(0.0, 1.0, size=n))
    return walk


def test_gamma_derived_from_hurst_positive_witness() -> None:
    """POSITIVE: real derive_gamma output satisfies gamma = 2H + 1 over a sweep.

    Algebraic invariant (INV-DRO1). For each seeded series the real estimator
    returns ``(gamma, H, r2)``; the measured residual ``|gamma - (2H+1)|`` must
    stay strictly below the documented ``1e-5`` ceiling. Calibration rows
    (H, gamma, residual) are printed for the evidence trail.
    """
    rows: list[tuple[int, float, float, float]] = []
    worst_residual = 0.0
    for seed in _POSITIVE_SEEDS:
        series = _seeded_random_walk(seed)
        gamma, hurst, r2 = derive_gamma(series)
        residual = abs(gamma - (2.0 * hurst + 1.0))
        worst_residual = max(worst_residual, residual)
        rows.append((seed, hurst, gamma, residual))

        assert math.isfinite(gamma) and math.isfinite(hurst) and math.isfinite(r2), (
            f"INV-DRO1 VIOLATED: derive_gamma returned non-finite "
            f"(gamma={gamma!r}, H={hurst!r}, r2={r2!r}) at seed={seed}. "
            f"DFA on a random walk must yield finite fields. "
            f"Source: Peng et al. 1994; core/dro_ara/engine.py::derive_gamma."
        )
        assert _gamma_consistent_with_hurst(gamma, hurst), (
            f"INV-DRO1 VIOLATED on seed={seed}: "
            f"|gamma - (2H+1)| = {residual:.3e} >= {_GAMMA_H_TOL:.0e}. "
            f"gamma={gamma!r}, H={hurst!r}. "
            f"gamma must be DERIVED from the DFA Hurst, never assigned "
            f"independently (Peng et al. 1994). "
            f"Source: core/dro_ara/engine.py::derive_gamma."
        )

    print("INV-DRO1 calibration (seed, H, gamma, residual):")
    for seed, hurst, gamma, residual in rows:
        print(f"  seed={seed:<5d} H={hurst:.6f} gamma={gamma:.6f} residual={residual:.3e}")
    assert worst_residual < _GAMMA_H_TOL, (
        f"INV-DRO1 VIOLATED: worst residual {worst_residual:.3e} over "
        f"{len(rows)} seeds exceeds {_GAMMA_H_TOL:.0e}. "
        f"gamma = 2H + 1 (Peng et al. 1994) must hold for every seed. "
        f"Source: core/dro_ara/engine.py::derive_gamma."
    )


def test_independent_gamma_assignment_is_rejected() -> None:
    """NEGATIVE: an independently-assigned gamma != 2H+1 is rejected, bad input fails closed.

    Two discriminating checks:

    1. derive_gamma is the ONLY source of gamma. We take the REAL measured H,
       then synthesise a tampered gamma that was assigned INDEPENDENTLY (not via
       2H+1). The defining predicate must REJECT it — proving the contract
       cannot be smuggled. The matching real gamma is accepted, so the predicate
       is genuinely discriminating, not vacuously false.
    2. Degenerate inputs (NaN / +Inf / -Inf / constant / too-short / non-1-D)
       must raise ValueError (INV-DRO5, fail-closed) — gamma is never fabricated
       from garbage.
    """
    # --- (1) tampered, independently-assigned gamma is caught --------------
    rejected = 0
    for seed in _POSITIVE_SEEDS:
        series = _seeded_random_walk(seed)
        real_gamma, hurst, _r2 = derive_gamma(series)
        # The real derivation must pass its own predicate (anchor).
        assert _gamma_consistent_with_hurst(real_gamma, hurst), (
            f"INV-DRO1 anchor failed: real gamma={real_gamma!r} inconsistent "
            f"with H={hurst!r} at seed={seed} — negative control would be vacuous."
        )
        # An attacker assigns gamma independently of H (offset well above tol).
        for tampered_gamma in (real_gamma + 0.5, 2.0 * hurst + 1.5, hurst):
            assert not _gamma_consistent_with_hurst(tampered_gamma, hurst), (
                f"INV-DRO1 VIOLATED: independently-assigned gamma="
                f"{tampered_gamma!r} was NOT rejected against H={hurst!r} "
                f"(residual {abs(tampered_gamma - (2.0 * hurst + 1.0)):.3e} "
                f"< {_GAMMA_H_TOL:.0e}). gamma must be derived, never smuggled. "
                f"Source: Peng et al. 1994; core/dro_ara/engine.py::derive_gamma."
            )
            rejected += 1
    assert rejected == len(_POSITIVE_SEEDS) * 3, (
        f"INV-DRO1 negative control under-covered: only {rejected} tampered "
        f"gammas exercised; expected {len(_POSITIVE_SEEDS) * 3}."
    )

    # --- (2) degenerate inputs fail closed (INV-DRO5) ----------------------
    nan_series = np.full(256, 1.0, dtype=np.float64)
    nan_series[100] = np.nan
    pos_inf_series = np.full(256, 1.0, dtype=np.float64)
    pos_inf_series[10] = np.inf
    neg_inf_series = np.full(256, 1.0, dtype=np.float64)
    neg_inf_series[200] = -np.inf
    constant_series = np.full(256, 3.14, dtype=np.float64)
    too_short_series = np.arange(5, dtype=np.float64)
    rank2_series = np.ones((16, 16), dtype=np.float64)

    degenerate: list[tuple[str, NDArray[np.float64], str]] = [
        ("nan", nan_series, "NaN/Inf"),
        ("pos_inf", pos_inf_series, "NaN/Inf"),
        ("neg_inf", neg_inf_series, "NaN/Inf"),
        ("constant", constant_series, "constant"),
        ("too_short", too_short_series, r"need ≥64"),
        ("rank2", rank2_series, "1-D"),
    ]
    for label, bad_series, expected in degenerate:
        with pytest.raises(ValueError, match=expected):
            derive_gamma(bad_series)
        # And: no fabricated gamma escapes — the call never returns a value.
        assert label  # tag retained for failure provenance
