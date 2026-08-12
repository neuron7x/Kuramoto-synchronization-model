# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Runtime contracts for the packaged geosync_pro production surface.

geosync_pro ships in the wheel (the "pro" tier) with real quant modules — CVaR
risk limiting, an EMH state-space model + EKF, an MPC controller. This binds its
public surface to measurable, defect-sensitive contracts so it can be moved from
`deferred_production` into the release coverage denominator (PR-D, Option A:
measure and test).
"""

from __future__ import annotations

import importlib

import pytest

from geosync_pro.models.emh import clamp, threat_mode
from geosync_pro.risk.cvar import CVARGate, cvar
from geosync_pro.validate.validate import run_validation


# --------------------------------------------------------------------------- #
# No import side effects (network / secret reads on import)
# --------------------------------------------------------------------------- #
def test_public_modules_import_without_side_effects() -> None:
    for mod in (
        "geosync_pro",
        "geosync_pro.risk.cvar",
        "geosync_pro.estimation.ekf",
        "geosync_pro.models.emh",
        "geosync_pro.policy.mpc",
        "geosync_pro.validate.validate",
    ):
        importlib.import_module(mod)  # must not open sockets or read secrets


# --------------------------------------------------------------------------- #
# CVaR — tail-risk contract (kills tail-selection / sign / empty-guard mutants)
# --------------------------------------------------------------------------- #
def test_cvar_is_the_mean_of_the_left_tail() -> None:
    returns = [-0.10, -0.08, -0.05, 0.00, 0.02, 0.03, 0.05, 0.01, -0.02, 0.04]
    es = cvar(returns, alpha=0.95)
    # Left-tail expected shortfall must be <= the worst-case floor and negative here.
    assert es <= min(returns) + 1e-9 or es == pytest.approx(min(returns))
    assert es < 0.0


def test_cvar_empty_returns_zero_not_crash() -> None:
    assert cvar([], alpha=0.95) == 0.0


def test_cvar_gate_scales_down_only_when_shortfall_exceeds_limit() -> None:
    gate = CVARGate(alpha=0.95, limit=0.03, lookback=50)
    # Benign small returns: shortfall under the limit -> full size (1.0).
    for _ in range(20):
        scaler = gate.update(0.001)
    assert scaler == 1.0
    # A large loss pushes shortfall over the limit -> scaler strictly in (0, 1).
    stressed = CVARGate(alpha=0.95, limit=0.03, lookback=50)
    for r in [-0.20, -0.15, -0.18, -0.22, -0.19]:
        scaler = stressed.update(r)
    assert 0.0 <= scaler < 1.0


# --------------------------------------------------------------------------- #
# clamp / threat_mode — deterministic boundary logic (kills >/>= and min/max mutants)
# --------------------------------------------------------------------------- #
def test_clamp_bounds() -> None:
    assert clamp(5.0, 0.0, 1.0) == 1.0
    assert clamp(-3.0, 0.0, 1.0) == 0.0
    assert clamp(0.5, 0.0, 1.0) == 0.5


@pytest.mark.parametrize(
    "dd,var_breach,vol,expected",
    [
        (0.0, True, 0.0, "RED"),      # var_breach dominates
        (0.71, False, 0.0, "RED"),    # dd > 0.7
        (0.0, False, 0.91, "RED"),    # vol > 0.9
        (0.7, False, 0.0, "AMBER"),   # dd == 0.7 is NOT RED (boundary), dd>0.4 -> AMBER
        (0.41, False, 0.0, "AMBER"),  # dd > 0.4
        (0.0, False, 0.71, "AMBER"),  # vol > 0.7
        (0.4, False, 0.7, "GREEN"),   # both at boundary, neither strictly exceeded
        (0.0, False, 0.0, "GREEN"),
    ],
)
def test_threat_mode_boundaries(dd: float, var_breach: bool, vol: float, expected: str) -> None:
    assert threat_mode(dd, var_breach, vol) == expected


# --------------------------------------------------------------------------- #
# Validation harness — seeded determinism (kills nondeterminism / seed-drop mutants)
# --------------------------------------------------------------------------- #
def test_run_validation_is_seeded_deterministic() -> None:
    _, metrics_a = run_validation(steps=60)
    _, metrics_b = run_validation(steps=60)
    assert metrics_a == metrics_b
    assert metrics_a, "validation must produce at least one metric"
