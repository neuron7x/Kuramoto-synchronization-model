# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the SynchronizationManifoldFrame (Task 4).

Falsifier witnesses: R outside [0, 1]; K < K_c but R above 3/√N after the
horizon; K > K_c but no order above that floor; phase data on a VIOLATED causal
cutoff (future L2); and a missing N or K_c. The builder reuses the existing
``order_parameter`` metric — no Kuramoto solver is duplicated.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from physics_contracts.manifold.contracts import CausalCutoffStatus
from physics_contracts.manifold.sync_frame import (
    SynchronizationManifoldFrame,
    build_sync_frame,
    finite_size_floor_for,
)

_N = 400


def _incoherent_theta(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-np.pi, np.pi, size=(200, _N))


def _coherent_theta() -> np.ndarray:
    return np.tile(np.linspace(0.0, 0.01, _N), (200, 1))


def _frame(**overrides: object) -> SynchronizationManifoldFrame:
    base: dict[str, Any] = {
        "snapshot_id": "snap",
        "R": 0.04,
        "finite_size_floor": finite_size_floor_for(_N),
        "phase_dispersion": 2.0,
        "locked_fraction": 0.0,
        "lyapunov_regime": "neutral",
        "causal_cutoff_status": CausalCutoffStatus.VALID,
        "validity_domain": "synthetic",
    }
    base.update(overrides)
    return SynchronizationManifoldFrame(**base)


def test_subcritical_happy_path() -> None:
    frame = build_sync_frame(
        snapshot_id="s",
        theta=_incoherent_theta(),
        coupling_K=0.1,
        critical_K=2.0,
        n_oscillators=_N,
        locked_fraction=0.0,
        lyapunov_regime="neutral",
        validity_domain="synthetic",
    )
    assert frame.R < frame.finite_size_floor
    assert frame.frame_digest == frame.frame_digest


def test_supercritical_happy_path() -> None:
    frame = build_sync_frame(
        snapshot_id="s",
        theta=_coherent_theta(),
        coupling_K=5.0,
        critical_K=2.0,
        n_oscillators=_N,
        locked_fraction=0.95,
        lyapunov_regime="stable",
        validity_domain="synthetic",
    )
    assert frame.R > frame.finite_size_floor


def test_R_outside_unit_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="INV-K1"):
        _frame(R=1.5)


def test_subcritical_with_order_above_floor_is_rejected() -> None:
    with pytest.raises(ValueError, match="subcritical_finite_size"):
        build_sync_frame(
            snapshot_id="s",
            theta=_coherent_theta(),  # R≈1 but we declare K<K_c
            coupling_K=0.1,
            critical_K=2.0,
            n_oscillators=_N,
            locked_fraction=0.0,
            lyapunov_regime="neutral",
            validity_domain="synthetic",
        )


def test_supercritical_without_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="frequency_entrainment"):
        build_sync_frame(
            snapshot_id="s",
            theta=_incoherent_theta(),  # R≈0 but we declare K>K_c
            coupling_K=5.0,
            critical_K=2.0,
            n_oscillators=_N,
            locked_fraction=0.9,
            lyapunov_regime="stable",
            validity_domain="synthetic",
        )


def test_violated_causal_cutoff_is_rejected() -> None:
    with pytest.raises(ValueError, match="causal_cutoff"):
        _frame(causal_cutoff_status=CausalCutoffStatus.VIOLATED)


def test_missing_critical_coupling_is_rejected() -> None:
    with pytest.raises(ValueError, match="frequency_entrainment"):
        build_sync_frame(
            snapshot_id="s",
            theta=_incoherent_theta(),
            coupling_K=0.1,
            critical_K=0.0,  # missing/invalid K_c
            n_oscillators=_N,
            locked_fraction=0.0,
            lyapunov_regime="neutral",
            validity_domain="synthetic",
        )


def test_missing_oscillator_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="subcritical_finite_size"):
        build_sync_frame(
            snapshot_id="s",
            theta=_incoherent_theta(),
            coupling_K=0.1,
            critical_K=2.0,
            n_oscillators=0,
            locked_fraction=0.0,
            lyapunov_regime="neutral",
            validity_domain="synthetic",
        )


def test_unknown_lyapunov_regime_is_rejected() -> None:
    with pytest.raises(ValueError, match="lyapunov_regime"):
        _frame(lyapunov_regime="exploding")
