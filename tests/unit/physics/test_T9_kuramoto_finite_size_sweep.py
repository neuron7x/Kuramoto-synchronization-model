# SPDX-License-Identifier: MIT
"""T9 (finite-size companion) — INV-K2 sweep across N and K ratios.

The companion file (`test_T9_kuramoto_transitions.py`) tests INV-K2
at one fixed ``(N=512, K=0.3·K_c, seed=42)``. INV-K2 is a *family*
of asymptotic claims:

    K < K_c ⟹ R(t→∞) → 0   with finite-size floor  ε = C/√N, C ∈ [2, 3].

A single-point check leaves the ``1/√N`` scaling untested. This
file widens the cell grid:

* ``N ∈ {64, 128, 256}`` — covers an octave-and-a-half of the
  ``1/√N`` law; default cells are kept compute-light so the suite
  remains under the standard test budget.
* ``k_ratio ∈ {0.1, 0.3}`` — two depths into the subcritical
  regime.
* Two seeds per cell — protects against a lucky-seed pass without
  blowing the runtime budget.

The bound asserted is ``R_final ≤ 3/√N`` (the upper end of the
catalog's ``[2, 3]`` epsilon range). A failure on a single cell
falsifies INV-K2.

The ``1/√N`` scaling test (which runs an N=512 simulation) is
gated behind ``@pytest.mark.heavy_math``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.engine import KuramotoEngine

_SIGMA_OMEGA: float = 1.0
_DT: float = 0.01
_STEPS: int = 1500


def _critical_coupling_gaussian(sigma: float) -> float:
    """K_c = 2·σ·√(2π)/π for a Gaussian frequency density."""
    return 2.0 * sigma * math.sqrt(2.0 * math.pi) / math.pi


def _run_R_tail_mean(N: int, coupling: float, seed: int) -> float:
    rng = np.random.default_rng(seed)
    omega = rng.normal(loc=0.0, scale=_SIGMA_OMEGA, size=N)
    theta0 = rng.uniform(-math.pi, math.pi, size=N)
    cfg = KuramotoConfig(
        N=N,
        K=coupling,
        omega=omega,
        theta0=theta0,
        dt=_DT,
        steps=_STEPS,
        seed=seed,
    )
    result = KuramotoEngine(cfg).run()
    tail = result.order_parameter[-(_STEPS // 3) :]
    return float(np.mean(tail))


@pytest.mark.parametrize("N", [64, 128, 256])
@pytest.mark.parametrize("k_ratio", [0.1, 0.3])
@pytest.mark.parametrize("seed", [7, 42])
def test_inv_k2_finite_size_floor(N: int, k_ratio: float, seed: int) -> None:
    """INV-K2: subcritical R_final ≤ 3/√N for every (N, k_ratio, seed) cell."""
    K_c = _critical_coupling_gaussian(_SIGMA_OMEGA)
    K = k_ratio * K_c
    floor_epsilon = 3.0 / math.sqrt(N)
    R_tail = _run_R_tail_mean(N=N, coupling=K, seed=seed)
    assert R_tail <= floor_epsilon, (
        f"INV-K2 VIOLATED on cell (N={N}, K/K_c={k_ratio}, seed={seed}): "
        f"R_tail={R_tail:.4f} > 3/√N = {floor_epsilon:.4f}. "
        f"Expected subcritical R bounded by finite-size noise floor "
        f"ε = 3/√N (catalog INV-K2). "
        f"Observed at sigma={_SIGMA_OMEGA}, K_c={K_c:.4f}, K={K:.4f}, "
        f"steps={_STEPS}, dt={_DT}. "
        "Physical reasoning: below K_c the only stable state is the "
        "incoherent fixed point; finite-N fluctuations leave R at the "
        "1/√N noise floor, not above it."
    )


@pytest.mark.heavy_math
def test_inv_k2_floor_scales_with_one_over_sqrt_n() -> None:
    """INV-K2: verify the 1/√N scaling, R_final(N=128) ≈ 2× R_final(N=512).

    This is a stronger property than any individual cell — it tests
    the *scaling law* itself. The ratio of tail-means across N
    should track the 1/√N prediction within a factor ≈ 2.

    Marked ``heavy_math`` because the N=512 simulation pushes the
    test runtime over the default per-test budget.
    """
    K_c = _critical_coupling_gaussian(_SIGMA_OMEGA)
    K = 0.3 * K_c
    seed = 42
    R_128 = _run_R_tail_mean(N=128, coupling=K, seed=seed)
    R_512 = _run_R_tail_mean(N=512, coupling=K, seed=seed)
    expected_ratio = math.sqrt(512.0 / 128.0)  # = 2.0
    measured_ratio = R_128 / max(R_512, 1e-12)
    assert 0.5 * expected_ratio <= measured_ratio <= 2.0 * expected_ratio, (
        f"INV-K2 SCALING VIOLATED: R(N=128)/R(N=512) = {measured_ratio:.3f}, "
        f"expected ≈ {expected_ratio:.3f} ± factor 2. "
        f"R_128={R_128:.4e}, R_512={R_512:.4e}. "
        "Physical reasoning: subcritical R follows the 1/√N "
        "finite-size law to leading order; deviation by more than a "
        "factor of 2 implies the engine's noise floor scales wrongly."
    )
