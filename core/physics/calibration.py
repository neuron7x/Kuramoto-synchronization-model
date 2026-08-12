# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics-invariant calibration harness.

This module turns the abstract question *"is our physics estimator
well-tuned?"* into a single function call returning a single
self-describing report. Every estimator in
``core.dro_ara`` and ``core.kuramoto`` rests on a P0 invariant from
CLAUDE.md; calibration is the operational test that the estimator
recovers a known ground truth on synthetic data **with the spec'd
tolerance**, not just that the algebraic identity holds (companion
file `tests/unit/physics/test_T_dro1_gamma_algebraic.py` already
covers identity).

Public surface
--------------

* :class:`CalibrationReport` — frozen dataclass; one row per
  (estimator, ground-truth value) pair. Carries the spec
  tolerance, observed error, and pass/fail verdict.
* :func:`calibrate_dro_hurst` — generates fBm with a target
  Hurst exponent, runs :func:`core.dro_ara.engine.derive_gamma`,
  reports recovery error against ``H_target``.
* :func:`calibrate_ott_antonsen_steady` — sweeps supercritical
  ``K/K_c`` ratios, runs the Ott–Antonsen engine, reports the
  steady-state recovery error against the analytical
  ``√(1 − 2Δ/K)``.
* :func:`run_calibration_suite` — runs both estimators across a
  default grid, returns a dict keyed by invariant ID with the
  full list of reports.
* :func:`format_markdown_table` — pretty-prints a list of
  reports as a Markdown table for CLI / CI artefact consumption.

What this module is *not*
-------------------------

It is **not** a "reality calibration" engine in any cosmic sense.
It is the engineering instrument that lets a developer ask
"does my physics still recover known ground truth at the documented
precision?" with one function call. Every report is anchored to a
specific INV-* ID; every tolerance comes from the catalog, not
from this module's opinion.

The fBm generator is the standard Davies & Harte (1987) circulant
embedding — exact for ``H ∈ (0, 1)`` to round-off, no truncation
bias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from core.dro_ara.engine import derive_gamma
from core.kuramoto.ott_antonsen import OttAntonsenEngine

__all__ = [
    "CalibrationReport",
    "calibrate_dro_hurst",
    "calibrate_ott_antonsen_steady",
    "format_markdown_table",
    "generate_fractional_brownian_motion",
    "run_calibration_suite",
]


# Spec tolerances anchored in CLAUDE.md ▸ INVARIANT REGISTRY.
_INV_DRO1_GAMMA_TOL: Final[float] = 1e-5
# DFA-Hurst recovery on N≈4096 fBm: empirical bias ≤ 0.07 in published
# benchmarks (Couillard & Davison 2005, Weron 2002). We use the
# generous 0.10 envelope, which is what the existing test suite
# implicitly assumes.
_DFA_HURST_RECOVERY_TOL: Final[float] = 0.10
# Ott–Antonsen integrator at dt=0.01, T=100: documented in
# tests/unit/physics/test_T23_ott_antonsen_chimera.py.
_OA_STEADY_RECOVERY_TOL: Final[float] = 1e-3


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Self-describing calibration outcome for one estimator / case.

    Attributes
    ----------
    estimator:
        Human-readable estimator name, e.g. ``"dro_dfa_hurst"``.
    invariant_id:
        The INV-* ID the estimator backs (catalog reference).
    case:
        Short label describing the ground-truth case
        (e.g. ``"H=0.5"``, ``"K=2.0,delta=0.5"``).
    ground_truth:
        Known true value of the quantity the estimator should
        recover.
    estimated:
        What the estimator returned.
    abs_error:
        ``|ground_truth − estimated|``. Always ``≥ 0``.
    spec_tolerance:
        Documented tolerance from the catalog (or, where the
        catalog is silent, the empirical envelope from peer-reviewed
        benchmarks). The pass/fail verdict uses this floor.
    passes:
        ``abs_error <= spec_tolerance``.
    n_samples:
        Length of the synthetic input fed to the estimator.
    seed:
        RNG seed used to generate the synthetic case.
    """

    estimator: str
    invariant_id: str
    case: str
    ground_truth: float
    estimated: float
    abs_error: float
    spec_tolerance: float
    passes: bool
    n_samples: int
    seed: int


def generate_fractional_brownian_motion(
    H: float,
    n: int,
    *,
    seed: int = 0,
) -> NDArray[np.float64]:
    """Generate fBm with target Hurst exponent ``H`` via Davies–Harte.

    Davies & Harte (1987), *Tests for Hurst effect*, Biometrika 74(1).
    The circulant embedding of the autocovariance produces fGn that is
    exact in distribution for ``H ∈ (0, 1)``, modulo IEEE-754 round-off
    in the FFT. The cumulative sum of the fGn is the fBm path returned.

    Parameters
    ----------
    H:
        Target Hurst exponent in ``(0, 1)``. ``H = 0.5`` is standard
        Brownian motion; ``H > 0.5`` is persistent; ``H < 0.5`` is
        anti-persistent.
    n:
        Output length. Internally the embedding works on a length-``2n``
        circulant matrix; ``n`` must be a positive integer.
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    Array of shape ``(n,)`` containing one fBm path.

    Raises
    ------
    ValueError
        If ``H`` is outside ``(0, 1)`` or ``n`` is not a positive
        integer.
    """
    if not (0.0 < H < 1.0):
        raise ValueError(f"H must lie in (0, 1); got {H!r}")
    if not isinstance(n, int) or n <= 0:
        raise ValueError(f"n must be a positive integer; got {n!r}")

    rng = np.random.default_rng(seed)
    # Step 1: autocovariance of fGn at lag k.
    k = np.arange(n)
    r = 0.5 * (
        np.power(np.abs(k + 1.0), 2.0 * H)
        - 2.0 * np.power(np.abs(k), 2.0 * H)
        + np.power(np.abs(k - 1.0), 2.0 * H)
    )
    # Step 2: build the symmetric extension for the circulant embedding.
    extended = np.concatenate([r, [0.0], r[1:][::-1]])
    eigenvalues = np.fft.fft(extended).real
    # Numerical floor: tiny negative eigenvalues from FFT round-off
    # are clipped to zero to keep √· well-defined.
    eigenvalues = np.where(eigenvalues < 0.0, 0.0, eigenvalues)
    # Step 3: complex Gaussian in spectral domain, scaled by √eigenvalues.
    m = 2 * n
    z = rng.standard_normal(m) + 1j * rng.standard_normal(m)
    spectrum = z * np.sqrt(eigenvalues / (2.0 * m))
    fgn_complex = np.fft.fft(spectrum)
    fgn = fgn_complex.real[:n]
    # Step 4: cumulative sum of fGn yields fBm.
    return np.cumsum(fgn).astype(np.float64)


def calibrate_dro_hurst(
    H_target: float,
    *,
    n: int = 4096,
    seed: int = 42,
) -> CalibrationReport:
    """Recover the Hurst exponent of synthetic geometric fBm via DRO-DFA.

    The ``derive_gamma`` estimator is calibrated for **price** input —
    its first step is ``diff(log(|x|))`` which only behaves as
    log-returns when the underlying process is positive (the standard
    geometric Brownian / geometric fBm assumption used by
    quantitative finance). Feeding raw fBm paths that cross zero
    produces ``log|x|`` artefacts unrelated to the Hurst exponent.

    This calibration therefore:

    1. Generates an fBm path with target Hurst ``H_target`` (the
       process intended to model log-prices);
    2. Exponentiates to get a positive price process
       ``P(t) = exp(fBm_H(t))``;
    3. Hands ``P(t)`` to :func:`derive_gamma`;
    4. Compares the recovered ``H`` to ``H_target``.

    Pass/fail uses the empirical DFA-Hurst envelope of ``0.10``.

    Parameters
    ----------
    H_target:
        Ground-truth Hurst exponent of the log-price process.
    n:
        Length of the synthetic fBm. Default 4096 — enough for DFA
        regression at scales 16…512 to converge.
    seed:
        RNG seed.
    """
    log_prices = generate_fractional_brownian_motion(H_target, n, seed=seed)
    # Geometric fBm: P(t) = exp(fBm(t)). Always positive, so the
    # log-returns inside derive_gamma are the original fGn(H_target).
    prices = np.exp(log_prices - log_prices.mean())
    _gamma, H_estimated, _r2 = derive_gamma(prices)
    abs_error = abs(H_estimated - H_target)
    return CalibrationReport(
        estimator="dro_dfa_hurst",
        invariant_id="INV-DRO1",
        case=f"H={H_target:.2f}",
        ground_truth=float(H_target),
        estimated=float(H_estimated),
        abs_error=float(abs_error),
        spec_tolerance=_DFA_HURST_RECOVERY_TOL,
        passes=bool(abs_error <= _DFA_HURST_RECOVERY_TOL),
        n_samples=n,
        seed=seed,
    )


def calibrate_ott_antonsen_steady(
    K: float,
    delta: float,
    *,
    T: float = 100.0,
    dt: float = 0.01,
    R0: float = 0.01,
    seed: int = 42,
) -> CalibrationReport:
    """Recover the supercritical steady-state R from the OA engine.

    Integrates the Ott–Antonsen ODE for the requested ``(K, Δ)`` pair
    and compares the long-time mean to the analytical
    ``R_∞ = √(1 − 2Δ/K)``. Requires ``K > 2Δ`` (supercritical).

    Parameters
    ----------
    K, delta:
        Coupling and Lorentzian half-width.
    T, dt, R0:
        Integration parameters. Defaults match the existing OA test.
    seed:
        Carried for parity with other calibrations; the OA engine is
        deterministic, so the seed has no effect on the trajectory.

    Raises
    ------
    ValueError
        If ``K ≤ 2·delta`` (subcritical / critical case has no
        analytical positive ``R_∞`` to recover).
    """
    if K <= 2.0 * delta:
        raise ValueError(
            "calibrate_ott_antonsen_steady requires K > 2·delta "
            f"(supercritical); got K={K}, delta={delta}, K_c={2.0 * delta}."
        )
    engine = OttAntonsenEngine(K=K, delta=delta)
    result = engine.integrate(T=T, dt=dt, R0=R0)
    R_analytical = math.sqrt(1.0 - 2.0 * delta / K)
    R_numerical = float(np.mean(result.R[-int(T / dt / 10) :]))
    abs_error = abs(R_numerical - R_analytical)
    return CalibrationReport(
        estimator="ott_antonsen_steady",
        invariant_id="INV-OA2",
        case=f"K={K},delta={delta}",
        ground_truth=R_analytical,
        estimated=R_numerical,
        abs_error=abs_error,
        spec_tolerance=_OA_STEADY_RECOVERY_TOL,
        passes=bool(abs_error <= _OA_STEADY_RECOVERY_TOL),
        n_samples=int(T / dt),
        seed=seed,
    )


def run_calibration_suite() -> dict[str, list[CalibrationReport]]:
    """Run the default calibration grid; return reports keyed by INV-* ID.

    Default grid:

    * INV-DRO1: ``H ∈ {0.3, 0.5, 0.7, 0.9}`` at ``n=4096``, seed=42.
    * INV-OA2: ``(K, Δ)`` cells covering the supercritical regime
      from ``K/K_c = 1.5`` to ``K/K_c = 10``.
    """
    dro_cases: list[CalibrationReport] = [
        calibrate_dro_hurst(H_target=h) for h in (0.3, 0.5, 0.7, 0.9)
    ]
    oa_cases: list[CalibrationReport] = [
        calibrate_ott_antonsen_steady(K=K, delta=delta)
        for K, delta in [
            (1.5, 0.5),
            (2.0, 0.5),
            (3.0, 0.5),
            (5.0, 0.5),
            (10.0, 0.5),
        ]
    ]
    return {
        "INV-DRO1": dro_cases,
        "INV-OA2": oa_cases,
    }


def format_markdown_table(reports: list[CalibrationReport]) -> str:
    """Pretty-print a list of reports as a Markdown table."""
    if not reports:
        return ""
    lines: list[str] = [
        "| INV | Estimator | Case | Truth | Estimated | |Error| | Tolerance | Pass |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        verdict = "✅" if r.passes else "❌"
        lines.append(
            f"| {r.invariant_id} | {r.estimator} | {r.case} | "
            f"{r.ground_truth:.4f} | {r.estimated:.4f} | "
            f"{r.abs_error:.2e} | {r.spec_tolerance:.0e} | {verdict} |"
        )
    return "\n".join(lines)


def _main() -> None:  # pragma: no cover - CLI entry, exercised manually
    suite = run_calibration_suite()
    flat: list[CalibrationReport] = []
    for reports in suite.values():
        flat.extend(reports)
    print(format_markdown_table(flat))
    n_pass = sum(1 for r in flat if r.passes)
    n_total = len(flat)
    print(f"\n**Calibration**: {n_pass}/{n_total} passed.")


if __name__ == "__main__":
    _main()
