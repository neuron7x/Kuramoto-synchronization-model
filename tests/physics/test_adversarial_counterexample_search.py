# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adversarial counterexample search — an ACTIVE optimizer hunts for a violation.

Random sampling explores the input space passively. This module turns a global
optimizer (scipy ``differential_evolution``) into an adversary whose objective is
to MAXIMISE the violation of each bounded law — actively steering toward any
counterexample. If a real global search cannot push a bound past tolerance, that
is far stronger evidence than passive fuzzing that the bound holds. Each positive
witness reuses the REAL solver; the negative control proves the adversary is
capable by pointing it at a deliberately-too-tight bound, which it DOES breach.
"""
from __future__ import annotations

import numpy as np

import pytest

from scipy.optimize import differential_evolution

from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.physics.ricci_kuramoto import compute_order_parameter

pytestmark = pytest.mark.heavy_math

_UNIT_SLACK = 1e-6
_SEED = 12345


def _max_abs_z(params: np.ndarray) -> float:
    """max|z(t)| of the OA trajectory for (K, delta, R0); 0 on invalid params."""
    coupling, delta, r0 = (float(v) for v in params)
    try:
        result = OttAntonsenEngine(K=coupling, delta=delta).integrate(T=20.0, dt=0.02, R0=r0)
    except (ValueError, FloatingPointError):
        return 0.0
    return float(np.abs(result.z).max())


def _max_order_parameter(phases: np.ndarray) -> float:
    """Order parameter R for a phase vector; the adversary controls the phases."""
    return compute_order_parameter(np.asarray(phases, dtype=np.float64))


def test_adversary_cannot_break_ott_antonsen_unit_disk() -> None:
    """INV-OA1: a global optimizer maximising max|z| over (K,delta,R0) stays <= 1.

    The unit disk is the exact invariant manifold of the OA flow. An adversary
    that actively tunes the parameters to escape it must still fail.
    """
    bounds = [(0.05, 8.0), (0.05, 4.0), (0.01, 0.99)]
    res = differential_evolution(
        lambda x: -_max_abs_z(x), bounds, maxiter=20, popsize=10, seed=_SEED, polish=False, tol=1e-7
    )
    worst = -res.fun
    assert worst <= 1.0 + _UNIT_SLACK, (
        f"INV-OA1 ADVERSARIALLY VIOLATED: global search drove max|z|={worst:.8f} > 1 "
        f"(slack={_UNIT_SLACK:.1e}) at params={res.x}. The unit disk must be invariant "
        f"under any (K, delta, R0)."
    )


def test_adversary_cannot_break_order_parameter_bound() -> None:
    """INV-K1: a global optimizer maximising R over a phase vector stays <= 1."""
    n = 8
    bounds = [(-np.pi, np.pi)] * n
    res = differential_evolution(
        lambda x: -_max_order_parameter(x), bounds, maxiter=20, popsize=12, seed=_SEED, polish=False, tol=1e-7
    )
    worst = -res.fun
    assert worst <= 1.0 + _UNIT_SLACK, (
        f"INV-K1 ADVERSARIALLY VIOLATED: global search drove R={worst:.8f} > 1 "
        f"(slack={_UNIT_SLACK:.1e}) over {n} phases. R = |mean(exp(i*theta))| <= 1 by construction."
    )


def test_adversary_is_capable_of_finding_a_planted_violation() -> None:
    """Negative control: the SAME adversary breaches a deliberately-too-tight bound.

    Proves the search is a real falsifier, not an optimizer that simply fails to
    improve: against a fake bound of 0.5 on max|z| (the true sup is ~1), the
    adversary MUST find a counterexample. If it could not, the positive witnesses
    above would be vacuous (a search that never finds anything).
    """
    fake_bound = 0.5
    bounds = [(0.05, 8.0), (0.05, 4.0), (0.01, 0.99)]
    res = differential_evolution(
        lambda x: -_max_abs_z(x), bounds, maxiter=20, popsize=10, seed=_SEED, polish=False, tol=1e-7
    )
    worst = -res.fun
    assert worst > fake_bound, (
        f"ADVERSARY INCAPABLE: global search reached only max|z|={worst:.6f} <= fake bound "
        f"{fake_bound}; it failed to breach a bound the true supremum (~1) clearly exceeds, "
        f"so the positive witnesses would be vacuous."
    )
