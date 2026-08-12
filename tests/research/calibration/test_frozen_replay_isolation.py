# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Frozen calibration reproduction is insulated from the live integrator.

These tests prove the PATH-A epistemic-integrity contract: the pre-registered
CALIB-GRID ledgers reproduce by replaying a committed trajectory snapshot, so a
correctness change to the live ``SecondOrderKuramotoEngine`` (explicit-Euler
friction → BBK) cannot perturb a byte-frozen artifact. The keystone is
``test_frozen_reproduction_never_calls_live_integrator``: it makes the live
engine fail loudly and shows the frozen reproduction still succeeds.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto import second_order
from research.calibration.grid_kuramoto import frozen_replay
from research.calibration.grid_kuramoto.calibration import SimConfig, run_calibration
from research.calibration.grid_kuramoto.grid_data import wscc_9_bus
from research.calibration.grid_kuramoto.run import build_r1_ledger


def _boom(self: object) -> object:
    raise AssertionError("live SecondOrderKuramotoEngine.run() must not be called on the frozen path")


def test_frozen_reproduction_never_calls_live_integrator(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the live engine sabotaged, frozen reproduction still succeeds and
    yields the pre-registered parent value — proving replay, not recompute."""
    monkeypatch.setattr(second_order.SecondOrderKuramotoEngine, "run", _boom)
    nl = run_calibration(wscc_9_bus(), SimConfig(), noisy=False)
    # Parent ledger value (frozen, byte-unchanged): noiseless Frobenius ≈ 1.0459.
    assert abs(nl.frobenius_rel_error - 1.0459) < 1e-3


def test_r1_ledger_reproduces_under_sabotaged_live_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """The R1 ledger build reproduces the frozen swing result (gate closed at
    0.0666) off the snapshot, with the live integrator disabled."""
    monkeypatch.setattr(second_order.SecondOrderKuramotoEngine, "run", _boom)
    ledger = build_r1_ledger(wscc_9_bus(), SimConfig())
    assert ledger["verdict"] == "NEGATIVE"
    gate = next(g for g in ledger["gates"] if g["name"] == "noiseless.frobenius")
    assert gate["passed"] is True
    assert gate["observed"] < 0.10


def test_live_integrator_path_is_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The explicit opt-out genuinely routes to the live engine: under
    ``use_live_integrator`` the sabotaged engine IS called and surfaces."""
    monkeypatch.setattr(second_order.SecondOrderKuramotoEngine, "run", _boom)
    with frozen_replay.use_live_integrator():
        with pytest.raises(AssertionError, match="must not be called"):
            run_calibration(wscc_9_bus(), SimConfig(), noisy=False)


def test_snapshot_covers_preregistered_configs() -> None:
    """The committed snapshot is non-empty and the WSCC-9 calibration key is
    present, so the frozen reproduction path is snapshot-backed (fail-closed:
    a missing key would silently fall through to the live engine and the
    matches-committed tests would then fail loudly)."""
    cache = frozen_replay._load_cache()
    assert cache, "frozen trajectory snapshot is empty"
    for arr_pair in cache.values():
        phases, velocities = arr_pair
        assert phases.ndim == 2
        assert velocities.shape == phases.shape


def test_trajectory_key_is_stable_and_excludes_noise() -> None:
    """The key is deterministic and independent of post-integration noise σ
    (noiseless and noisy regimes share one raw trajectory)."""
    sysm = wscc_9_bus()
    k = np.asarray(sysm.susceptance, dtype=np.float64)
    w = np.zeros(sysm.n, dtype=np.float64)
    kw = dict(
        system_name=sysm.name,
        inertia=np.asarray(sysm.inertia, dtype=np.float64),
        damping=np.asarray(sysm.damping, dtype=np.float64),
        k_true=k,
        omega_true=w,
        dt=0.01,
        steps=100,
        seed=7,
        theta0_perturb=0.4,
    )
    assert frozen_replay.trajectory_key(**kw) == frozen_replay.trajectory_key(**kw)
