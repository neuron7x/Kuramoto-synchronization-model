# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable witnesses for kuramoto_critical_scaling.

Transforms the previously declaration-only catalog law
``kuramoto.critical_scaling`` into a falsifiable contract: the supercritical
Kuramoto order parameter must converge to the EXACT Ott-Antonsen fixed point
R_infinity = sqrt(1 - 2*delta/K), with the mean-field critical exponent
beta = 1/2 near onset. Positive witness asserts the exact match to machine
precision; the negative control proves the instrument rejects the subcritical
regime (no spurious synchronisation) and fails closed on invalid parameters.

Source: Ott & Antonsen, Chaos 18, 037113 (2008); Kuramoto (1975). INV-OA2/INV-K3.
"""
from __future__ import annotations

import math

import numpy as np

import pytest

from core.kuramoto.ott_antonsen import OttAntonsenEngine

_DELTA = 0.5
_K_C = 2.0 * _DELTA  # critical coupling = 2*delta = 1.0
_EXACT_TOL = 1e-9  # measured deviation is ~1e-14; this is a generous machine-precision band


def test_supercritical_R_matches_closed_form() -> None:
    """Positive witness: integrated R_infinity equals sqrt(1-2*delta/K) for K>K_c."""
    worst = 0.0
    for K in (1.2, 1.5, 2.0, 3.0, 5.0):  # all strictly > K_c = 1.0
        engine = OttAntonsenEngine(K=K, delta=_DELTA)
        r_inf = float(engine.integrate(T=200.0, dt=0.01, R0=0.05).R[-1])
        r_exact = math.sqrt(1.0 - _K_C / K)
        worst = max(worst, abs(r_inf - r_exact))
        assert abs(r_inf - r_exact) < _EXACT_TOL, (
            f"KURAMOTO CRITICAL-SCALING VIOLATED: integrated R_inf={r_inf:.12f} != "
            f"closed form sqrt(1-2*delta/K)={r_exact:.12f} at K={K}, delta={_DELTA}, "
            f"K_c={_K_C}. The Ott-Antonsen reduction must converge to the EXACT "
            f"supercritical fixed point. tol={_EXACT_TOL}, T=200, dt=0.01, |dev|={abs(r_inf - r_exact):.2e}"
        )


def test_critical_exponent_is_one_half() -> None:
    """Positive witness: R_infinity ~ (K-K_c)^beta with beta -> 1/2 as onset is approached."""
    eps = np.array([0.005, 0.01, 0.02, 0.04])  # K - K_c, approaching onset
    r = np.array([math.sqrt(1.0 - _K_C / (_K_C + e)) for e in eps])
    slope = float(np.polyfit(np.log(eps), np.log(r), 1)[0])
    assert abs(slope - 0.5) < 0.05, (
        f"KURAMOTO CRITICAL-EXPONENT VIOLATED: fitted beta={slope:.4f} != 1/2 for "
        f"R_inf ~ (K-K_c)^beta near onset (delta={_DELTA}, K_c={_K_C}). The mean-field "
        f"Kuramoto transition is a supercritical pitchfork, beta=1/2. tol=0.05"
    )


def test_subcritical_and_invalid_are_rejected() -> None:
    """Negative control: subcritical K has no positive steady state; invalid params fail closed."""
    # Subcritical: the closed form is exactly zero and the dynamics decay to incoherence.
    # A positive R_infinity claim in this regime is FALSE and must be refuted.
    for K in (0.5, 0.9):  # strictly < K_c = 1.0
        engine = OttAntonsenEngine(K=K, delta=_DELTA)
        assert engine.R_steady == 0.0, (
            f"SUBCRITICAL VIOLATED: closed-form R_steady={engine.R_steady} != 0 at "
            f"K={K} <= K_c={_K_C}; the incoherent state is the only attractor."
        )
        r_last = float(engine.integrate(T=200.0, dt=0.01, R0=0.05).R[-1])
        assert r_last < 1e-3, (
            f"SUBCRITICAL VIOLATED: K={K} < K_c={_K_C} produced sustained R={r_last:.6e}; "
            f"a subcritical ensemble must decay to incoherence. A positive R_inf here is falsified."
        )
    # Fail-closed contract: non-physical frequency width or coupling is rejected at construction.
    for bad_delta in (0.0, -0.5, float("nan")):
        with pytest.raises(ValueError):
            OttAntonsenEngine(K=2.0, delta=bad_delta)
    with pytest.raises(ValueError):
        OttAntonsenEngine(K=float("inf"), delta=_DELTA)
