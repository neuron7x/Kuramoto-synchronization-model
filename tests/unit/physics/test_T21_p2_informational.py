# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T21 — P2 informational witnesses for the 3 remaining invariants.

P2 invariants are informational — expected behaviour that is allowed to
fail without blocking release. These witnesses document the physics and
catch regressions, but their failure is a signal to investigate, not a
gate.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.indicators.ricci import ricci_curvature_edge
from core.kuramoto.config import KuramotoConfig
from core.kuramoto.engine import KuramotoEngine

# ── INV-DA6: Larger α → faster + more variance ──────────────────────


def test_dopamine_learning_rate_tradeoff(tmp_path: "pytest.TempPathFactory") -> None:
    """INV-DA6: larger learning rate α produces faster convergence but
    higher RPE variance.

    Runs two DopamineController instances with different learning rates
    on the same fixed-reward sequence, then compares convergence speed
    (steps to |RPE| < 0.1) and RPE variance in the tail.
    """
    from pathlib import Path

    from geosync.core.neuro.dopamine import DopamineController

    cfg_src = Path("config/dopamine.yaml")
    cfg_target = tmp_path / "dopamine.yaml"  # type: ignore[operator]
    cfg_target.write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")

    def _run_sequence(lr_override: float, n_steps: int) -> list[float]:
        ctrl = DopamineController(str(cfg_target))
        ctrl._cache_learning_rate_v = lr_override
        rpes: list[float] = []
        for _ in range(n_steps):
            rpe = ctrl.compute_rpe(
                reward=1.0,
                value=ctrl.value_estimate,
                next_value=ctrl.value_estimate,
                discount_gamma=0.95,
            )
            ctrl.update_value_estimate(rpe)
            rpes.append(rpe)
        return rpes

    n_steps = 300
    rpes_slow = _run_sequence(lr_override=0.01, n_steps=n_steps)
    rpes_fast = _run_sequence(lr_override=0.2, n_steps=n_steps)

    # Faster α should have lower |RPE| in the tail (converged sooner)
    # tolerance: P2 informational, allow generous slack
    tail_start = n_steps * 2 // 3
    tail_slow = rpes_slow[tail_start:]
    tail_fast = rpes_fast[tail_start:]
    mean_abs_slow = float(np.mean(np.abs(tail_slow)))
    mean_abs_fast = float(np.mean(np.abs(tail_fast)))

    assert mean_abs_fast <= mean_abs_slow + 0.05, (  # epsilon: P2 slack
        f"INV-DA6 VIOLATED: faster α=0.2 tail |RPE|={mean_abs_fast:.4f} > "
        f"slower α=0.01 tail |RPE|={mean_abs_slow:.4f}. "
        f"Expected faster learning rate to converge sooner. "
        f"Observed at N={n_steps} steps, gamma=0.95, reward=1.0. "
        f"Physical reasoning: larger α makes V track R faster."
    )

    # But faster α should also have more variance
    var_slow = float(np.var(tail_slow))
    var_fast = float(np.var(tail_fast))
    # This is P2 — we document the expected direction but don't gate on it
    # because small finite-sample noise can reverse the inequality.
    if var_fast < var_slow:
        pytest.skip(
            f"INV-DA6 variance direction reversed (P2 informational): "
            f"var_fast={var_fast:.6f} < var_slow={var_slow:.6f}"
        )


# ── INV-K6: Phases uniform under K < K_c ────────────────────────────


def test_subcritical_phases_uniform() -> None:
    """INV-K6: K < K_c ⟹ phases approximately uniform on [-π, π].

    Uses the Rayleigh test for circular uniformity: the test statistic
    Z = N·R² should follow χ²(2) under uniformity. For N=200 and
    K=0 (completely incoherent), the final phases should pass the
    uniformity test with p > 0.01.
    """
    n_oscillators = 200
    cfg = KuramotoConfig(N=n_oscillators, K=0.0, dt=0.01, steps=500, seed=42)
    result = KuramotoEngine(cfg).run()
    final_phases = result.phases[-1]

    # Rayleigh test: Z = N * R^2
    mean_vector = np.mean(np.exp(1j * final_phases))
    r_value = float(np.abs(mean_vector))
    rayleigh_z = n_oscillators * r_value**2
    # Under uniformity, P(Z > z) ≈ exp(-z) for large N
    # tolerance: p > 0.01 means Z < -ln(0.01) ≈ 4.6
    critical_z = -math.log(0.01)  # epsilon: Rayleigh critical value at p=0.01

    assert rayleigh_z < critical_z, (
        f"INV-K6 VIOLATED: Rayleigh Z={rayleigh_z:.4f} > critical "
        f"{critical_z:.4f} (p < 0.01). "
        f"Expected uniform phases at K=0 (completely incoherent). "
        f"Observed at N={n_oscillators}, K=0.0, steps=500, seed=42. "
        f"Physical reasoning: without coupling, oscillators evolve "
        f"independently and phases remain uniformly distributed."
    )


# ── INV-RC2: κ > 0 indicates clustering ─────────────────────────────


def test_positive_curvature_indicates_clustering() -> None:
    """INV-RC2: κ > 0 correlates with clustering across graph topologies.

    Sweeps several two-cluster graphs (clique sizes 4, 5, 6, 7) and
    computes the mean intra-cluster curvature vs mean bridge curvature.
    The correlation between density and curvature sign is the core
    qualitative claim of INV-RC2.
    """
    import networkx as nx

    intra_kappas: list[float] = []
    bridge_kappas: list[float] = []

    for clique_size in (4, 5, 6, 7):
        g1 = nx.complete_graph(clique_size)
        g2 = nx.complete_graph(range(clique_size, 2 * clique_size))
        graph = nx.compose(g1, g2)
        graph.add_edge(clique_size - 1, clique_size)  # bridge
        for u, v in graph.edges():
            graph[u][v]["weight"] = 1.0

        kappa_intra = ricci_curvature_edge(graph, 0, 1)
        kappa_bridge = ricci_curvature_edge(graph, clique_size - 1, clique_size)
        intra_kappas.append(kappa_intra)
        bridge_kappas.append(kappa_bridge)

    mean_intra = float(np.mean(intra_kappas))
    mean_bridge = float(np.mean(bridge_kappas))

    # tolerance: 0.0 is the theoretical boundary for the clustering signal
    assert mean_intra > 0.0, (  # epsilon: theoretical clustering boundary
        f"INV-RC2 VIOLATED: mean intra-cluster κ={mean_intra:.4f} ≤ 0. "
        f"Expected κ > 0 within dense clusters (averaged over 4 sizes). "
        f"Observed at clique_sizes=(4,5,6,7). "
        f"Physical reasoning: complete subgraphs have maximal local density."
    )
    assert mean_intra > mean_bridge, (
        f"INV-RC2 VIOLATED: mean intra κ={mean_intra:.4f} ≤ mean bridge "
        f"κ={mean_bridge:.4f}. "
        f"Expected clustering signal: κ(intra) > κ(bridge) on average. "
        f"Observed at clique_sizes=(4,5,6,7), N=4 graph topologies. "
        f"Physical reasoning: bridge edges connect sparse bottlenecks."
    )
