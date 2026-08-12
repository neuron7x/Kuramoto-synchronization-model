# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable witnesses for the catalog law ``kuramoto.subcritical_finite_size``.

LAW (physics_contracts/catalog.yaml :: kuramoto.subcritical_finite_size):
    Below the critical coupling the Kuramoto order parameter sits on a
    finite-size noise floor, ``<r> ~ c / sqrt(N)`` (incoherent state), with
    ``c = O(1)`` for Lorentzian frequencies. Canonical tolerance: ``r < 3/sqrt(N)``
    with ``p >= 0.99`` over ``M >= 200`` trials. Validity: ``K <= 0.8*K_c``,
    ``N >= 256``, equilibration ``t > 20/gamma`` (``gamma`` = Lorentzian
    half-width, ``K_c = 2*gamma``). Source: Strogatz 2000; Daido 1990; Hong
    et al. PRE 2007. Routed invariants: INV-K2 (``K < K_c => R -> 0``) and
    INV-K5 (``<R> ~ O(1/sqrt(N))`` incoherent).

EMPIRICAL CALIBRATION (this file's regime, engine = core.kuramoto.engine RK4
all-to-all, Lorentzian omega via standard_cauchy, gamma = 1.0, K_c = 2.0):
  * The clean ``1/sqrt(N)`` floor lives DEEP subcritical. At ``K = 0.8*K_c``
    (the validity edge) critical susceptibility enhances the floor and the
    coefficient grows with N, so the bare finite-size floor is masked. This
    executable witness therefore runs at ``K = 0.3*K_c`` (well inside
    ``K <= 0.8*K_c``), where the finite-size floor is the active regime.
  * The test now slices ONLY samples with ``t > 20/gamma``. Earlier versions
    averaged the last half of a ``t=21`` trajectory, which included samples from
    ``t=10.5`` and could certify transient behavior. The current default uses
    ``t=31`` with a 210-sample post-equilibration tail beginning at ``t=20.5``.
    The robust anchors are the canonical ``r < 3/sqrt(N)`` tolerance plus the
    bounded, near-constant coefficient ``c = <r>*sqrt(N)`` (c constant <=>
    r ~ 1/sqrt(N)); the slope carries only a wide corroborating band.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.engine import KuramotoEngine

pytestmark = pytest.mark.heavy_math

# --- physical regime (Lorentzian: K_c = 2*gamma) -----------------------------
GAMMA: float = 1.0
K_C: float = 2.0 * GAMMA
K_SUB: float = 0.3 * K_C  # deep subcritical, well inside validity K <= 0.8*K_c
K_SUPER: float = 1.5 * K_C  # supercritical, for the negative control

DT: float = 0.05
EQUILIBRATION_TIME: float = 20.0 / GAMMA
POST_EQUILIBRATION_STEP: int = int(np.floor(EQUILIBRATION_TIME / DT)) + 1
STEPS: int = 620  # t = 31.0; with TAIL=210 the returned slice starts at t=20.5
TAIL: int = 210  # post-equilibration tail only: t in [20.5, 31.0]
BASE_SEED: int = 20240617

# N >= 256 (validity). Time-averaging over the tail yields M = n_seeds*TAIL
# quasi-independent asymptotic order-parameter samples per N (M >= 200 each).
SUBCRITICAL_PLAN: dict[int, int] = {256: 4, 384: 2, 512: 2}

# --- calibrated tolerances (see module docstring) ----------------------------
C_LO: float = 0.5  # noise-floor coefficient band, c = <r>*sqrt(N)
C_HI: float = 1.8
C_RATIO_MAX: float = 2.0  # c ~ const <=> r ~ 1/sqrt(N) (observed ratio 1.47)
SLOPE_LO: float = -1.45  # wide corroboration band; excludes flat/supercritical
SLOPE_HI: float = -0.15  # high-statistics reference is close to -0.5
FLOOR_P: float = 0.99  # canonical catalog tolerance: P(r < 3/sqrt(N)) >= 0.99
M_MIN: int = 200  # canonical catalog tolerance: M >= 200 trials
SOURCE: str = "Strogatz 2000; Daido 1990; Hong et al. PRE 2007"


def _equilibrated_order_parameter(
    n_osc: int, seed: int, coupling: float, steps: int = STEPS
) -> NDArray[np.float64]:
    """Return only post-equilibration order-parameter samples for one ensemble.

    Uses the canonical RK4 all-to-all integrator (``core.kuramoto.engine``) and a
    Lorentzian (Cauchy) natural-frequency draw of half-width ``GAMMA``; no bespoke
    physics is implemented here. The returned slice is fail-closed: every sample
    starts strictly after ``t > 20/gamma`` and the caller still receives at least
    ``TAIL`` samples for the witness budget.
    """
    if steps <= POST_EQUILIBRATION_STEP + TAIL - 1:
        raise ValueError(
            "Kuramoto finite-size witness under-sampled: steps must leave a full "
            f"post-equilibration tail after t>{EQUILIBRATION_TIME:.1f}; "
            f"got steps={steps}, required >= {POST_EQUILIBRATION_STEP + TAIL}."
        )
    rng = np.random.default_rng(BASE_SEED + 1009 * seed + n_osc)
    omega: NDArray[np.float64] = (rng.standard_cauchy(n_osc) * GAMMA).astype(np.float64)
    theta0: NDArray[np.float64] = rng.uniform(0.0, 2.0 * np.pi, n_osc).astype(np.float64)
    cfg = KuramotoConfig(
        N=n_osc, K=coupling, omega=omega, theta0=theta0, dt=DT, steps=steps, seed=seed
    )
    order_parameter = np.asarray(KuramotoEngine(cfg).run().order_parameter, dtype=np.float64)
    start = max(POST_EQUILIBRATION_STEP, int(order_parameter.size) - TAIL)
    samples = order_parameter[start:]
    assert samples.size >= TAIL, (
        "INV-K5 UNDER-SAMPLED: post-equilibration slice returned "
        f"{samples.size} samples < required tail {TAIL}; steps={steps}, "
        f"post_equilibration_step={POST_EQUILIBRATION_STEP}."
    )
    return np.asarray(samples, dtype=np.float64)


def _ensemble_tail(
    n_osc: int, n_seeds: int, coupling: float, steps: int = STEPS
) -> NDArray[np.float64]:
    """Concatenate post-equilibration tail samples across ``n_seeds`` seeds for one N."""
    return np.concatenate(
        [_equilibrated_order_parameter(n_osc, s, coupling, steps) for s in range(n_seeds)]
    )


def test_subcritical_order_parameter_obeys_inverse_sqrt_n_noise_floor() -> None:
    """Positive witness: K < K_c leaves r on the c/sqrt(N) finite-size noise floor.

    Robust anchors (sampling-stable): the canonical ``P(r < 3/sqrt(N)) >= 0.99``
    over ``M >= 200`` tolerance, and the bounded near-constant coefficient
    ``c = <r>*sqrt(N)`` (constant c <=> r ~ 1/sqrt(N)). The log-log slope is a
    wide corroborating band only (see module docstring).
    """
    n_values: list[int] = []
    mean_r: list[float] = []
    coeffs: list[float] = []

    for n_osc, n_seeds in SUBCRITICAL_PLAN.items():
        samples = _ensemble_tail(n_osc, n_seeds, K_SUB)
        n_trials = int(samples.size)
        floor = 3.0 / np.sqrt(n_osc)
        p_below = float(np.mean(samples < floor))
        r_mean = float(samples.mean())
        coeff = r_mean * float(np.sqrt(n_osc))

        assert n_trials >= M_MIN, (
            f"INV-K5 UNDER-SAMPLED: M={n_trials} < {M_MIN} trials at N={n_osc}. "
            f"Catalog requires M >= 200 asymptotic samples after t>{EQUILIBRATION_TIME:.1f}. "
            f"K={K_SUB:.3f}, K_c={K_C:.3f}, gamma={GAMMA}, t={STEPS * DT:.1f}. "
            f"Source: {SOURCE}"
        )
        # Canonical catalog tolerance (INV-K2 finite-size bound r < 3/sqrt(N)).
        assert p_below >= FLOOR_P, (
            f"INV-K2 VIOLATED: P(r < 3/sqrt(N))={p_below:.4f} < required {FLOOR_P} "
            f"expected the subcritical order parameter under the 3/sqrt(N)={floor:.4f} "
            f"finite-size floor. K={K_SUB:.3f}, K_c={K_C:.3f}, N={n_osc}, M={n_trials}, "
            f"post-equilibration t>{EQUILIBRATION_TIME:.1f}, end_t={STEPS * DT:.1f}. Source: {SOURCE}"
        )
        # Noise-floor magnitude: c = <r>*sqrt(N) is O(1) (~sqrt(pi/2)=1.2533).
        assert C_LO <= coeff <= C_HI, (
            f"INV-K5 VIOLATED: c=<r>*sqrt(N)={coeff:.4f} left band [{C_LO}, {C_HI}] "
            f"expected an O(1) noise-floor coefficient (Lorentzian c ~ sqrt(pi/2)). "
            f"<r>={r_mean:.5f}, K={K_SUB:.3f}, K_c={K_C:.3f}, N={n_osc}. "
            f"Source: {SOURCE}"
        )
        n_values.append(n_osc)
        mean_r.append(r_mean)
        coeffs.append(coeff)

    # <r> strictly decreases with N (a floor cannot grow with system size).
    for i in range(len(n_values) - 1):
        assert mean_r[i] > mean_r[i + 1], (
            f"INV-K5 VIOLATED: <r> not decreasing: <r>(N={n_values[i]})={mean_r[i]:.5f} "
            f"<= <r>(N={n_values[i + 1]})={mean_r[i + 1]:.5f} "
            f"expected a 1/sqrt(N) floor that shrinks with N. "
            f"K={K_SUB:.3f}, K_c={K_C:.3f}, gamma={GAMMA}. Source: {SOURCE}"
        )

    # c ~ constant across N is the defining signature of r ~ 1/sqrt(N).
    c_ratio = max(coeffs) / min(coeffs)
    assert c_ratio < C_RATIO_MAX, (
        f"INV-K5 VIOLATED: c=<r>*sqrt(N) ratio max/min={c_ratio:.4f} >= {C_RATIO_MAX} "
        f"expected a constant coefficient (r ~ 1/sqrt(N)); growth signals a "
        f"different scaling. coeffs={[round(c, 4) for c in coeffs]}, N={n_values}. "
        f"Source: {SOURCE}"
    )

    # log-log slope corroboration (wide band; sampling-sensitive, see docstring).
    log_n = np.log(np.asarray(n_values, dtype=np.float64))
    log_r = np.log(np.asarray(mean_r, dtype=np.float64))
    slope = float(np.polyfit(log_n, log_r, 1)[0])
    assert SLOPE_LO <= slope <= SLOPE_HI, (
        f"INV-K5 VIOLATED: log<r> vs logN slope={slope:.4f} left band "
        f"[{SLOPE_LO}, {SLOPE_HI}] expected ~ -0.5 (r ~ 1/sqrt(N)); a near-zero "
        f"slope would mean a coherent O(1) parameter, not a finite-size floor. "
        f"K={K_SUB:.3f}, K_c={K_C:.3f}, N={n_values}. Source: {SOURCE}"
    )


def test_supercritical_breaks_noise_floor_and_invalid_inputs_fail_closed() -> None:
    """Negative control: the 1/sqrt(N) floor is FALSIFIED above K_c, and bad inputs raise.

    Plants a real violation: for ``K > K_c`` the order parameter is O(1)
    (partially synchronized), so the subcritical claim ``r < 3/sqrt(N)`` is false
    and ``c = r*sqrt(N)`` GROWS with N instead of staying constant. Also asserts
    the engine fails closed on contract-violating inputs (no silent garbage R).
    """
    r_super: list[float] = []
    c_super: list[float] = []
    for n_osc in (256, 512):
        samples = _equilibrated_order_parameter(n_osc, 0, K_SUPER)
        r_mean = float(samples.mean())
        floor = 3.0 / np.sqrt(n_osc)
        # Supercritical r is O(1) -- a coherent state, not a vanishing floor.
        assert r_mean > 0.3, (
            f"NEG-CONTROL INVALID: supercritical <r>={r_mean:.4f} not O(1) at "
            f"N={n_osc}, K={K_SUPER:.3f} > K_c={K_C:.3f}; expected partial sync. "
            f"R_inf=sqrt(1-K_c/K)={np.sqrt(max(0.0, 1.0 - K_C / K_SUPER)):.3f}. "
            f"Source: {SOURCE}"
        )
        # The subcritical noise-floor claim is FALSIFIED here (r >> 3/sqrt(N)).
        assert r_mean > floor, (
            f"NEG-CONTROL INVALID: supercritical <r>={r_mean:.4f} did not exceed the "
            f"subcritical floor 3/sqrt(N)={floor:.4f} expected the 1/sqrt(N) claim to "
            f"be falsified for K={K_SUPER:.3f} > K_c={K_C:.3f}, N={n_osc}. Source: {SOURCE}"
        )
        r_super.append(r_mean)
        c_super.append(r_mean * float(np.sqrt(n_osc)))

    # c = r*sqrt(N) GROWS with N supercritically -- the opposite of a flat floor.
    assert c_super[1] > c_super[0], (
        f"NEG-CONTROL INVALID: supercritical c=<r>*sqrt(N) did not grow with N: "
        f"c(256)={c_super[0]:.3f}, c(512)={c_super[1]:.3f}. A genuine 1/sqrt(N) floor "
        f"keeps c constant; here it must DIVERGE. K={K_SUPER:.3f}, K_c={K_C:.3f}. "
        f"Source: {SOURCE}"
    )

    # Fail-closed: contract-violating inputs raise (pydantic ValidationError is a
    # ValueError subclass) -- no silent garbage order parameter is ever produced.
    with pytest.raises(ValueError):
        KuramotoConfig(N=1, K=K_SUB, dt=DT, steps=10, seed=0)  # N < 2 (N=0/1 degenerate)
    with pytest.raises(ValueError):
        KuramotoConfig(N=8, K=float("nan"), dt=DT, steps=10, seed=0)  # non-finite K
    with pytest.raises(ValueError):
        KuramotoConfig(N=8, K=float("inf"), dt=DT, steps=10, seed=0)  # non-finite K
    with pytest.raises(ValueError):
        KuramotoConfig(  # non-finite gamma -> non-finite omega
            N=8, K=K_SUB, omega=np.full(8, np.inf), dt=DT, steps=10, seed=0
        )
