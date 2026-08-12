# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for Kuramoto-Ricci geometric flow engine."""

from __future__ import annotations

import time

import numpy as np

from core.kuramoto import KuramotoConfig, KuramotoEngine
from core.kuramoto.ricci_flow_engine import KuramotoRicciFlowEngine


def _engine(**kwargs: object) -> KuramotoRicciFlowEngine:
    cfg = KuramotoConfig(
        N=kwargs.pop("N", 12),
        K=kwargs.pop("K", 1.0),
        dt=0.02,
        steps=kwargs.pop("steps", 120),
        seed=7,
    )
    return KuramotoRicciFlowEngine(cfg, **kwargs)


def test_coupling_bounds() -> None:
    engine = _engine(curvature_method="forman", ricci_update_interval=5)
    result = engine.run()
    max_k = engine.K_base * engine.sigma
    assert np.all(result.coupling_matrix_history >= -1e-12)
    assert np.all(result.coupling_matrix_history <= max_k + 1e-12)


def test_symmetric_coupling() -> None:
    engine = _engine(curvature_method="forman", ricci_update_interval=5)
    result = engine.run()
    assert np.allclose(
        result.coupling_matrix_history,
        np.swapaxes(result.coupling_matrix_history, 1, 2),
        atol=1e-12,
    )


def test_no_self_coupling() -> None:
    engine = _engine(curvature_method="forman", ricci_update_interval=4)
    result = engine.run()
    diag = np.diagonal(result.coupling_matrix_history, axis1=1, axis2=2)
    assert np.allclose(diag, 0.0, atol=1e-12)


def test_curvature_feedback() -> None:
    engine = _engine(curvature_method="forman", ricci_update_interval=1, steps=2)

    def _positive(*_args: object, **_kwargs: object) -> dict[tuple[int, int], float]:
        graph, edges = _args[0], _args[1]
        _ = graph
        return {edge: 0.9 for edge in edges}

    engine._compute_edge_curvature_map = _positive  # type: ignore[method-assign]
    result = engine.run()
    means = [
        float(np.mean(snapshot[np.triu_indices(engine._cfg.N, k=1)]))
        for snapshot in result.coupling_matrix_history
    ]
    baseline = engine.K_base / engine._cfg.N
    assert max(means) > baseline


def test_fallback_on_error() -> None:
    engine = _engine(curvature_method="ollivier", ricci_update_interval=1, steps=3)

    def _boom(*_args: object, **_kwargs: object) -> dict[tuple[int, int], float]:
        raise RuntimeError("forced ricci failure")

    engine._compute_edge_curvature_map = _boom  # type: ignore[method-assign]
    result = engine.run()
    expected = engine.K_base / engine._cfg.N
    first = result.coupling_matrix_history[0]
    offdiag = first[np.triu_indices(engine._cfg.N, k=1)]
    assert np.allclose(offdiag, expected)


def test_herding_detection() -> None:
    engine = _engine(curvature_method="forman", ricci_update_interval=1, steps=4)

    def _herding(*_args: object, **_kwargs: object) -> dict[tuple[int, int], float]:
        _, edges = _args
        return {edge: 0.7 for edge in edges}

    engine._compute_edge_curvature_map = _herding  # type: ignore[method-assign]
    result = engine.run()
    assert result.herding_index.size > 0
    assert float(result.herding_index[-1]) > 0.8


def test_fragmentation() -> None:
    engine = _engine(curvature_method="forman", ricci_update_interval=1, steps=5)
    calls = {"n": 0}

    def _frag(*_args: object, **_kwargs: object) -> dict[tuple[int, int], float]:
        _, edges = _args
        kappa = -0.1 - 0.1 * calls["n"]
        calls["n"] += 1
        return {edge: kappa for edge in edges}

    engine._compute_edge_curvature_map = _frag  # type: ignore[method-assign]
    result = engine.run()
    assert result.fragility_index[-1] > result.fragility_index[0]


def test_deterministic() -> None:
    e1 = _engine(curvature_method="forman", ricci_update_interval=4, steps=60)
    e2 = _engine(curvature_method="forman", ricci_update_interval=4, steps=60)
    r1 = e1.run()
    r2 = e2.run()
    np.testing.assert_allclose(r1.phases, r2.phases)
    np.testing.assert_allclose(r1.order_parameter, r2.order_parameter)
    np.testing.assert_allclose(r1.coupling_matrix_history, r2.coupling_matrix_history)


def test_order_parameter_bounds() -> None:
    engine = _engine(curvature_method="forman", ricci_update_interval=3)
    result = engine.run()
    assert np.all((result.order_parameter >= 0.0) & (result.order_parameter <= 1.0))


def test_performance() -> None:
    cfg = KuramotoConfig(N=100, K=1.2, dt=0.01, steps=1000, seed=3)
    engine = KuramotoRicciFlowEngine(
        cfg,
        curvature_method="forman",
        ricci_update_interval=100,
        correlation_window=32,
        graph_threshold=0.4,
    )
    start = time.perf_counter()
    _ = engine.run()
    elapsed = time.perf_counter() - start
    assert elapsed < 30.0


def test_coupling_history_can_be_disabled() -> None:
    engine = _engine(
        curvature_method="forman", ricci_update_interval=2, coupling_history_enabled=False
    )
    result = engine.run()
    assert result.coupling_matrix_history.shape == (0, engine._cfg.N, engine._cfg.N)
    assert result.curvature_timestamps.size > 0


def test_feedback_changes_dynamics_vs_standard_kuramoto() -> None:
    cfg = KuramotoConfig(N=24, K=1.5, dt=0.02, steps=160, seed=11)
    base = KuramotoEngine(cfg).run()
    flow = KuramotoRicciFlowEngine(
        cfg,
        curvature_method="forman",
        ricci_update_interval=1,
        graph_threshold=0.0,
        damping=0.0,
    ).run()
    assert not np.allclose(base.order_parameter, flow.order_parameter)


def test_ollivier_mode_does_not_silently_fallback() -> None:
    engine = _engine(
        curvature_method="ollivier", N=8, steps=10, ricci_update_interval=1, graph_threshold=0.0
    )
    fallback_hit = {"value": False}
    original = engine._recompute_coupling

    def _wrapped(
        corr_buffer: list[np.ndarray],
        prev_coupling: np.ndarray,
        n: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        coupling, kappa_vec = original(corr_buffer, prev_coupling, n)
        if kappa_vec.size == 0:
            fallback_hit["value"] = True
        return coupling, kappa_vec

    engine._recompute_coupling = _wrapped  # type: ignore[method-assign]
    _ = engine.run()
    assert fallback_hit["value"] is False
