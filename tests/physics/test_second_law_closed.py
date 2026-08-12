# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for second_law_closed (thermodynamics: dS/dt >= 0, no external work).

Executable falsification contract for the catalog law ``thermo.second_law_closed``
(maps to INV-TH2 / INV-ST3: entropy production >= 0). The physical model reuses
the exact overdamped-Langevin primitive
:func:`core.physics.stochastic_thermodynamics.langevin_ensemble_step` — no
thermodynamics is hand-rolled here.

Scope (stated precisely so the law is falsifiable, not vacuous)
---------------------------------------------------------------
A single overdamped degree of freedom in a harmonic well ``V = ½ k x²`` coupled
to a heat bath. The Gibbs (differential) entropy of the zero-mean Gaussian
ensemble is ``S = ½ ln(2π e · Var(x))`` nats.

* POSITIVE witness — a *closed* subsystem with **no external work**: the ensemble
  is prepared out of equilibrium, NARROWER than the well's Boltzmann width
  (``Var₀ = kT/k₀`` with ``k₀ > k``), then left to relax in a FIXED well
  (``dk = 0`` ⇒ Sekimoto work ``dW = ½ x² dk = 0``). It approaches equilibrium by
  free expansion and its Gibbs entropy is non-decreasing, ``dS/dt >= 0``.

* NEGATIVE control — an *open* system with **external work / negentropy
  injection**: an external agent stiffens the confinement (compression,
  ``k₀ < k``), doing work on the subsystem and driving its entropy DOWN. The
  closed-subsystem witness must DETECT the entropy decrease (``min dS`` far below
  the band), falsifying the closed/no-work claim for that driven process. A
  non-finite / non-positive thermal context additionally fails closed.

Tolerance band
--------------
``_DS_TOL = 0.02`` nats. The per-block entropy estimate has finite-ensemble
sampling SE ``≈ ½·sqrt(2/(M−1)) ≈ 3.5e-3`` for ``M = 40000``; a block-to-block
difference carries ``sqrt(2)×`` that ``≈ 5e-3``. The band is ~4× that
Monte-Carlo noise floor (measured worst per-block ``min dS ≈ −6e-3`` on the
plateau), well below the ``+0.70`` nat free-expansion signal. It is grounded in
1/√M sampling noise, not a tuned constant.

Fixed seeds, vectorized ensemble; runtime a few seconds.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
import pytest

from core.physics.stochastic_thermodynamics import langevin_ensemble_step

FloatArray = npt.NDArray[np.float64]

_KT: float = 1.0
_GAMMA: float = 1.0
_DT: float = 0.005
_ENSEMBLE: int = 40_000
_N_BLOCKS: int = 24
_BLOCK_STEPS: int = 50
# Block-difference sampling-noise band: ~4 · sqrt(2) · ½·sqrt(2/(M−1)), M=40000.
_DS_TOL: float = 0.02


def _gaussian_entropy(variance: float) -> float:
    """Gibbs differential entropy of a zero-mean Gaussian, in nats: ½·ln(2π e·Var)."""
    if not math.isfinite(variance) or variance <= 0.0:
        raise ValueError(f"variance must be a positive finite float, got {variance!r}")
    return 0.5 * math.log(2.0 * math.pi * math.e * variance)


def _relaxation_entropy(seed: int, *, k_release: float, var0: float) -> FloatArray:
    r"""Gibbs-entropy trajectory of an ensemble relaxing in a FIXED harmonic well.

    The ensemble is prepared as a zero-mean Gaussian of variance ``var0`` (the
    Boltzmann state of a well of stiffness ``kT/var0``) and then relaxed in a
    fixed well of stiffness ``k_release`` (``dk = 0`` ⇒ no external work). Entropy
    is recorded at the start and after each block of Langevin steps.

    Returns the entropy trajectory of length ``_N_BLOCKS + 1`` (nats).
    """
    rng = np.random.default_rng(seed)
    x: FloatArray = rng.standard_normal(_ENSEMBLE) * math.sqrt(var0)
    entropies: list[float] = [_gaussian_entropy(float(np.var(x)))]
    for _ in range(_N_BLOCKS):
        for _ in range(_BLOCK_STEPS):
            x = langevin_ensemble_step(
                x, k=k_release, dt=_DT, kT=_KT, gamma=_GAMMA, rng=rng
            )
        entropies.append(_gaussian_entropy(float(np.var(x))))
    return np.asarray(entropies, dtype=np.float64)


def test_closed_subsystem_entropy_nondecreases() -> None:
    """Positive witness: free relaxation (no external work) has dS/dt >= 0.

    Prepares the subsystem narrower than its Boltzmann width (Var₀ = kT/k₀,
    k₀ = 4) and releases it into a fixed softer well (k = 1, dk = 0 ⇒ dW = 0).
    The Gibbs entropy rises monotonically toward equilibrium; every block-to-block
    increment stays at or above the −_DS_TOL sampling band (INV-TH2 / INV-ST3).
    """
    worst_min_dS = math.inf
    smallest_total = math.inf
    for seed in (1, 7, 42, 123):
        entropy = _relaxation_entropy(seed, k_release=1.0, var0=_KT / 4.0)
        d_entropy = np.diff(entropy)
        min_dS = float(d_entropy.min())
        total_dS = float(entropy[-1] - entropy[0])
        worst_min_dS = min(worst_min_dS, min_dS)
        smallest_total = min(smallest_total, total_dS)
        assert min_dS >= -_DS_TOL, (
            f"INV-TH2/INV-ST3 VIOLATED: min dS={min_dS:.5f} < -tol={-_DS_TOL:.5f} "
            f"for a closed (dk=0, no external work) subsystem. "
            f"Expected entropy production dS/dt >= 0 during free relaxation to "
            f"equilibrium (Gibbs S=½·ln(2πe·Var)). Band = ~4·sqrt(2/(M-1)) "
            f"Monte-Carlo noise. At k0=4, k_release=1.0, kT={_KT:.1f}, "
            f"ensemble={_ENSEMBLE}, blocks={_N_BLOCKS}, seed={seed}."
        )
    # Non-vacuous: the entropy must actually rise by a wide margin over the band,
    # otherwise the dS>=0 assertion would be trivially satisfiable by a flat S.
    assert smallest_total > 0.5, (
        f"INV-TH2/INV-ST3 setup degenerate: total entropy rise {smallest_total:.4f} "
        f"nats is not >> band {_DS_TOL:.3f}; the free-expansion signal vanished. "
        f"Expected ΔS ≈ ½·ln(k0/k_release) = ½·ln(4) ≈ 0.693 nats. "
        f"worst per-block min dS={worst_min_dS:+.5f}."
    )


def test_external_work_injection_is_detected() -> None:
    """Negative control: external compression work drives dS < 0 and is detected.

    An open process: an external agent stiffens the confinement (k0=1 -> k=4),
    injecting work / negentropy that compresses the ensemble below equilibrium and
    DECREASES its Gibbs entropy. The closed-subsystem witness must flag the
    decrease (min dS far below -tol) — the closed/no-work claim is false here.
    A non-finite / non-positive thermal context additionally fails closed.
    """
    entropy = _relaxation_entropy(7, k_release=4.0, var0=_KT / 1.0)
    d_entropy = np.diff(entropy)
    min_dS = float(d_entropy.min())
    total_dS = float(entropy[-1] - entropy[0])
    assert min_dS < -_DS_TOL, (
        f"INV-TH2/INV-ST3 negative control inert: min dS={min_dS:.5f} did NOT breach "
        f"-tol={-_DS_TOL:.5f}. Expected external compression work (k0=1 -> k=4) to "
        f"DROP Gibbs entropy (open/driven process, not closed). "
        f"Measured total dS={total_dS:.4f} nats. The witness failed to discriminate "
        f"a negentropy injection from a closed relaxation."
    )
    assert total_dS < -0.5, (
        f"INV-TH2/INV-ST3 negative control weak: total dS={total_dS:.4f} nats not "
        f"<< 0; the injected-work compression must strongly reduce entropy "
        f"(ΔS ≈ ½·ln(k0/k) = ½·ln(1/4) ≈ -0.693 nats)."
    )
    # Fail-closed: an unphysical thermal context is rejected, not silently run.
    with pytest.raises(ValueError, match="must be a positive finite float"):
        langevin_ensemble_step(
            np.zeros(8, dtype=np.float64),
            k=1.0,
            dt=_DT,
            kT=-1.0,
            gamma=_GAMMA,
            rng=np.random.default_rng(0),
        )
