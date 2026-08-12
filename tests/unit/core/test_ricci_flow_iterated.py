# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the iterated Ricci-flow + surgery wrapper.

These tests guard the iterated-step API gap surfaced by the falsification
battery (`falsify_ricci_surgery.py`). Single-step INV-RC-FLOW remains the
contract owner; this file documents and pins the iterated-loop semantics
(``IteratedRicciFlowResult.aborted_reason``, drift / connectedness arrays).

Reference: ``docs/research/ricci_flow_surgery.md`` — "Iterated-Step Semantics".
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pytest
from numpy.typing import NDArray

from core.kuramoto.ricci_flow import (
    IteratedRicciFlowResult,
    RicciFlowConfig,
    iterated_ricci_flow_with_surgery,
    ricci_flow_with_surgery,
)


def _er_weights(n: int, p: float, seed: int) -> NDArray[np.float64]:
    """Reproducible Erdős–Rényi weight matrix used by the falsification battery."""
    rng = np.random.default_rng(seed)
    adj = rng.random((n, n)) < p
    adj |= adj.T
    np.fill_diagonal(adj, False)
    weights = rng.random((n, n)) * adj.astype(np.float64)
    weights = 0.5 * (weights + weights.T)
    np.fill_diagonal(weights, 0.0)
    return weights.astype(np.float64, copy=False)


def _constant_negative_curvature_fn(
    kappa: float = -0.5,
) -> object:
    """Return a curvature_fn that emits κ on every active upper-triangular edge."""

    def fn(W: NDArray[np.float64]) -> Mapping[tuple[int, int], float]:
        out: dict[tuple[int, int], float] = {}
        n = W.shape[0]
        iu, ju = np.triu_indices(n, k=1)
        for i, j, w in zip(iu.tolist(), ju.tolist(), W[iu, ju].tolist(), strict=True):
            if w > 0.0:
                out[(int(i), int(j))] = float(kappa)
        return out

    return fn


def test_iterated_wrapper_aborts_on_mass_drift_or_disconnect() -> None:
    """Reproduce the falsification-battery setup: 100-step ER loop on default cfg.

    The wrapper must EITHER abort with a structured reason before the contract
    breaks OR record a trajectory that stayed within bounds. Either branch is
    acceptable; silent breakage is not.
    """
    weights = _er_weights(n=10, p=0.4, seed=20260425)
    curvature_fn = _constant_negative_curvature_fn(kappa=-0.5)

    cfg = RicciFlowConfig(
        preserve_total_edge_mass=True,
        preserve_connectedness=True,
    )
    result = iterated_ricci_flow_with_surgery(
        weights,
        curvature_fn,  # type: ignore[arg-type]
        n_steps=100,
        cfg=cfg,
        max_mass_drift=0.10,
        abort_on_disconnect=True,
    )

    assert isinstance(result, IteratedRicciFlowResult)
    assert result.n_steps_requested == 100
    assert result.mass_drift_per_step.shape == (result.n_steps_executed,)
    assert result.connectedness_per_step.shape == (result.n_steps_executed,)
    assert np.all(result.mass_drift_per_step >= 0.0)

    if result.aborted_reason is not None:
        assert result.aborted_reason in {
            "mass_drift_exceeded",
            "disconnected",
            "step_failed",
        }
        assert result.n_steps_executed < 100
    else:
        assert result.n_steps_executed == 100
        assert bool(np.all(result.mass_drift_per_step <= 0.10)), (
            "INV-RC-FLOW-ITER VIOLATED: drift exceeded threshold without abort; "
            f"observed max_drift={float(result.mass_drift_per_step.max()):.6e}, "
            f"expected <= 0.10, with N=10, n_steps=100, seed=20260425."
        )
        assert bool(np.all(result.connectedness_per_step)), (
            "INV-RC-FLOW-ITER VIOLATED: graph disconnected without abort; "
            f"observed connected={result.connectedness_per_step.tolist()}, "
            "expected all True, with preserve_connectedness=True."
        )


def test_iterated_wrapper_zero_steps_returns_initial() -> None:
    """``n_steps=0`` is a no-op: returns the initial weights unchanged with empty trajectories."""
    weights = _er_weights(n=8, p=0.5, seed=1)
    curvature_fn = _constant_negative_curvature_fn(kappa=-0.5)
    cfg = RicciFlowConfig()

    result = iterated_ricci_flow_with_surgery(
        weights,
        curvature_fn,  # type: ignore[arg-type]
        n_steps=0,
        cfg=cfg,
    )

    assert result.n_steps_executed == 0
    assert result.n_steps_requested == 0
    assert result.aborted_reason is None
    assert result.mass_drift_per_step.shape == (0,)
    assert result.connectedness_per_step.shape == (0,)
    np.testing.assert_array_equal(result.final_weights, weights)
    # Zero-step path must NOT alias the caller's array (defensive copy).
    assert result.final_weights is not weights


def test_iterated_wrapper_records_one_step_correctly() -> None:
    """``n_steps=1`` matches a direct ``ricci_flow_with_surgery`` call bit-identically."""
    weights = _er_weights(n=6, p=0.6, seed=42)
    curvature_fn = _constant_negative_curvature_fn(kappa=-0.3)
    cfg = RicciFlowConfig(eta=0.05, preserve_connectedness=True)

    direct = ricci_flow_with_surgery(weights, dict(curvature_fn(weights)), cfg)  # type: ignore[operator]
    iterated = iterated_ricci_flow_with_surgery(
        weights,
        curvature_fn,  # type: ignore[arg-type]
        n_steps=1,
        cfg=cfg,
    )

    np.testing.assert_array_equal(iterated.final_weights, direct.weights_after)
    assert iterated.n_steps_executed == 1
    assert iterated.n_steps_requested == 1
    assert iterated.aborted_reason is None
    assert iterated.mass_drift_per_step.shape == (1,)
    assert iterated.connectedness_per_step.shape == (1,)


def test_iterated_wrapper_deterministic() -> None:
    """Fixed seed → bit-identical drift trajectory across two runs."""
    weights = _er_weights(n=10, p=0.4, seed=20260425)
    curvature_fn = _constant_negative_curvature_fn(kappa=-0.5)
    cfg = RicciFlowConfig(
        preserve_total_edge_mass=True,
        preserve_connectedness=True,
    )

    r1 = iterated_ricci_flow_with_surgery(
        weights,
        curvature_fn,  # type: ignore[arg-type]
        n_steps=20,
        cfg=cfg,
        max_mass_drift=0.50,  # loose bound so we get a long trajectory
    )
    r2 = iterated_ricci_flow_with_surgery(
        weights,
        curvature_fn,  # type: ignore[arg-type]
        n_steps=20,
        cfg=cfg,
        max_mass_drift=0.50,
    )

    assert r1.n_steps_executed == r2.n_steps_executed
    assert r1.aborted_reason == r2.aborted_reason
    np.testing.assert_array_equal(r1.mass_drift_per_step, r2.mass_drift_per_step)
    np.testing.assert_array_equal(r1.connectedness_per_step, r2.connectedness_per_step)
    np.testing.assert_array_equal(r1.final_weights, r2.final_weights)


def test_iterated_wrapper_negative_n_steps_rejected() -> None:
    """Negative ``n_steps`` is rejected fail-closed."""
    weights = _er_weights(n=4, p=0.5, seed=0)
    curvature_fn = _constant_negative_curvature_fn()
    with pytest.raises(ValueError, match="n_steps"):
        iterated_ricci_flow_with_surgery(
            weights,
            curvature_fn,  # type: ignore[arg-type]
            n_steps=-1,
            cfg=RicciFlowConfig(),
        )


def test_iterated_wrapper_invalid_drift_threshold_rejected() -> None:
    """Non-finite or negative ``max_mass_drift`` is rejected fail-closed."""
    weights = _er_weights(n=4, p=0.5, seed=0)
    curvature_fn = _constant_negative_curvature_fn()
    with pytest.raises(ValueError, match="max_mass_drift"):
        iterated_ricci_flow_with_surgery(
            weights,
            curvature_fn,  # type: ignore[arg-type]
            n_steps=1,
            cfg=RicciFlowConfig(),
            max_mass_drift=-0.1,
        )
    with pytest.raises(ValueError, match="max_mass_drift"):
        iterated_ricci_flow_with_surgery(
            weights,
            curvature_fn,  # type: ignore[arg-type]
            n_steps=1,
            cfg=RicciFlowConfig(),
            max_mass_drift=float("inf"),
        )
