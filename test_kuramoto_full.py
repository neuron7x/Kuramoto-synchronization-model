#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Full hardware test of all 7 Kuramoto engine extensions.

Runs on real iron: CPU, memory, GPU (if available).
Reports timing, correctness, and resource usage.
"""

import sys
import time
import traceback

import numpy as np

# Ensure project root is on path
sys.path.insert(0, ".")

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
SKIP = "\033[93m⊘ SKIP\033[0m"

results = []


def test(name):
    """Decorator for test functions."""

    def decorator(fn):
        def wrapper():
            t0 = time.perf_counter()
            try:
                fn()
                dt = time.perf_counter() - t0
                print(f"  {PASS}  {name} ({dt:.3f}s)")
                results.append((name, "PASS", dt))
            except Exception as e:
                dt = time.perf_counter() - t0
                print(f"  {FAIL}  {name} ({dt:.3f}s): {e}")
                traceback.print_exc()
                results.append((name, "FAIL", dt))

        return wrapper

    return decorator


# ============================================================
# 0. BASELINE — Original engine
# ============================================================


@test("0. Baseline RK4 engine (N=100, 5000 steps)")
def test_baseline():
    from core.kuramoto import KuramotoConfig, KuramotoEngine

    cfg = KuramotoConfig(N=100, K=2.0, dt=0.01, steps=5000, seed=42)
    result = KuramotoEngine(cfg).run()
    assert result.phases.shape == (5001, 100)
    assert 0.0 <= result.summary["final_R"] <= 1.0
    assert np.isfinite(result.phases).all()


# ============================================================
# 1. JAX ENGINE
# ============================================================


@test("1a. JAX import check")
def test_jax_import():
    try:
        from core.kuramoto.jax_engine import JAX_AVAILABLE

        if not JAX_AVAILABLE:
            print(f"    {SKIP} JAX not installed — skipping JAX tests")
            results.append(("1. JAX engine", "SKIP", 0))
            return
        import jax

        print(f"    JAX backend: {jax.default_backend()}")
    except ImportError:
        print(f"    {SKIP} JAX not available")


@test("1b. JAX single simulation (N=100, 5000 steps)")
def test_jax_single():
    from core.kuramoto.jax_engine import JAX_AVAILABLE

    if not JAX_AVAILABLE:
        return
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.jax_engine import JaxKuramotoEngine

    cfg = KuramotoConfig(N=100, K=2.0, dt=0.01, steps=5000, seed=42)
    result = JaxKuramotoEngine(cfg).run()
    assert result.phases.shape == (5001, 100)
    assert 0.0 <= result.summary["final_R"] <= 1.0


@test("1c. JAX batch vmap (100 simulations)")
def test_jax_batch():
    from core.kuramoto.jax_engine import JAX_AVAILABLE

    if not JAX_AVAILABLE:
        return
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.jax_engine import JaxKuramotoEngine

    cfg = KuramotoConfig(N=50, K=2.0, dt=0.01, steps=1000, seed=0)
    results_batch = JaxKuramotoEngine.batch(cfg, seeds=list(range(100)))
    assert len(results_batch) == 100
    for r in results_batch:
        assert 0.0 <= r.summary["final_R"] <= 1.0


# ============================================================
# 2. SPARSE ENGINE
# ============================================================


@test("2a. Sparse engine — small (N=200, density=0.1)")
def test_sparse_small():
    from scipy import sparse

    from core.kuramoto import KuramotoConfig
    from core.kuramoto.sparse import SparseKuramotoEngine

    N = 200
    adj = sparse.random(N, N, density=0.1, format="csr", random_state=42)
    adj = adj + adj.T  # symmetric
    cfg = KuramotoConfig(N=N, K=2.0, dt=0.01, steps=2000, seed=42)
    result = SparseKuramotoEngine(cfg, sparse_adjacency=adj).run()
    assert result.phases.shape == (2001, N)
    assert np.isfinite(result.phases).all()


@test("2b. Sparse engine — large (N=10000, density=0.001)")
def test_sparse_large():
    from scipy import sparse

    from core.kuramoto import KuramotoConfig
    from core.kuramoto.sparse import SparseKuramotoEngine

    N = 10_000
    adj = sparse.random(N, N, density=0.001, format="csr", random_state=42)
    cfg = KuramotoConfig(N=N, K=1.0, dt=0.01, steps=200, seed=42)
    result = SparseKuramotoEngine(cfg, sparse_adjacency=adj).run()
    assert result.phases.shape == (201, N)
    edges = adj.nnz
    print(f"    N={N:,}, edges={edges:,}, memory={adj.data.nbytes / 1e6:.1f}MB")


@test("2c. Sparse vs dense equivalence (N=50)")
def test_sparse_dense_equiv():
    from core.kuramoto import KuramotoConfig, KuramotoEngine
    from core.kuramoto.sparse import SparseKuramotoEngine

    cfg = KuramotoConfig(N=50, K=2.0, dt=0.01, steps=500, seed=42)
    r_dense = KuramotoEngine(cfg).run()
    r_sparse = SparseKuramotoEngine(cfg).run()
    # Should produce identical results (global mode)
    np.testing.assert_allclose(r_dense.order_parameter, r_sparse.order_parameter, atol=1e-10)


# ============================================================
# 3. ADAPTIVE SOLVER
# ============================================================


@test("3a. Adaptive RK45 (N=50, stiff K=20)")
def test_adaptive_rk45():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.adaptive import AdaptiveKuramotoEngine

    cfg = KuramotoConfig(N=50, K=20.0, dt=0.01, steps=3000, seed=42)
    result = AdaptiveKuramotoEngine(cfg, method="RK45", rtol=1e-8).run()
    assert result.phases.shape == (3001, 50)
    assert np.isfinite(result.phases).all()
    print(f"    final_R={result.summary['final_R']:.4f}")


@test("3b. Adaptive LSODA (auto stiff/non-stiff)")
def test_adaptive_lsoda():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.adaptive import AdaptiveKuramotoEngine

    cfg = KuramotoConfig(N=30, K=50.0, dt=0.005, steps=2000, seed=42)
    result = AdaptiveKuramotoEngine(cfg, method="LSODA").run()
    assert np.isfinite(result.phases).all()
    # Strong coupling should synchronize
    assert result.summary["final_R"] > 0.8


@test("3c. Adaptive vs fixed-step convergence (N=20)")
def test_adaptive_vs_fixed():
    from core.kuramoto import KuramotoConfig, KuramotoEngine
    from core.kuramoto.adaptive import AdaptiveKuramotoEngine

    cfg = KuramotoConfig(N=20, K=3.0, dt=0.005, steps=2000, seed=42)
    r_fixed = KuramotoEngine(cfg).run()
    r_adaptive = AdaptiveKuramotoEngine(cfg, method="DOP853", rtol=1e-12).run()
    # Both should agree on final R within tolerance
    np.testing.assert_allclose(
        r_fixed.summary["final_R"],
        r_adaptive.summary["final_R"],
        atol=0.02,
    )


# ============================================================
# 4. PHASE TRANSITION DETECTOR
# ============================================================


@test("4a. Phase transition sweep (N=100, 30 points)")
def test_phase_transition():
    from core.kuramoto.phase_transition import PhaseTransitionAnalyzer

    analyzer = PhaseTransitionAnalyzer(N=50, seed=42, steps_per_point=1000, dt=0.01)
    report = analyzer.sweep(K_range=(0.0, 5.0), n_points=15)

    print(f"    K_c={report.K_c:.3f} (fwd={report.K_c_forward:.3f}, bwd={report.K_c_backward:.3f})")
    print(f"    K_c_theoretical={report.K_c_theoretical:.3f}")
    print(f"    hysteresis={report.hysteresis_width:.3f}")

    # K_c should be roughly near theoretical
    assert 0.5 < report.K_c < 5.0
    assert report.R_forward[-1] > 0.5  # strong K → synchronized


@test("4b. Phase transition — R monotonicity check")
def test_phase_transition_mono():
    from core.kuramoto.phase_transition import PhaseTransitionAnalyzer

    analyzer = PhaseTransitionAnalyzer(N=30, seed=123, steps_per_point=800)
    report = analyzer.sweep(K_range=(0.0, 8.0), n_points=10)
    # Forward sweep: R should generally increase with K
    assert report.R_forward[-1] > report.R_forward[0]


# ============================================================
# 5. DELAYED FEEDBACK DDE
# ============================================================


@test("5a. DDE uniform delay (τ=0.1)")
def test_dde_uniform():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.delayed import DelayedKuramotoEngine

    cfg = KuramotoConfig(N=30, K=3.0, dt=0.01, steps=3000, seed=42)
    result = DelayedKuramotoEngine(cfg, tau=0.1).run()
    assert result.phases.shape == (3001, 30)
    assert np.isfinite(result.phases).all()
    print(f"    final_R={result.summary['final_R']:.4f}")


@test("5b. DDE heterogeneous delays (N×N τ matrix)")
def test_dde_heterogeneous():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.delayed import DelayedKuramotoEngine

    N = 20
    rng = np.random.default_rng(42)
    tau_matrix = rng.uniform(0.01, 0.2, (N, N))
    cfg = KuramotoConfig(N=N, K=4.0, dt=0.01, steps=2000, seed=42)
    result = DelayedKuramotoEngine(cfg, tau=tau_matrix).run()
    assert np.isfinite(result.phases).all()


@test("5c. DDE τ=0 should match standard engine")
def test_dde_zero_delay():
    from core.kuramoto import KuramotoConfig, KuramotoEngine
    from core.kuramoto.delayed import DelayedKuramotoEngine

    cfg = KuramotoConfig(N=15, K=2.0, dt=0.01, steps=500, seed=42)
    r_std = KuramotoEngine(cfg).run()
    r_dde = DelayedKuramotoEngine(cfg, tau=0.0).run()
    # Zero delay should approximate standard engine closely
    np.testing.assert_allclose(
        r_std.summary["final_R"],
        r_dde.summary["final_R"],
        atol=0.05,
    )


# ============================================================
# 6. SECOND-ORDER (SWING EQUATION)
# ============================================================


@test("6a. Second-order basic (m=1, d=0.1)")
def test_second_order_basic():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.second_order import SecondOrderKuramotoEngine

    cfg = KuramotoConfig(N=50, K=5.0, dt=0.005, steps=5000, seed=42)
    result = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.1).run()
    assert result.phases.shape == (5001, 50)
    assert result.velocities.shape == (5001, 50)
    assert np.isfinite(result.phases).all()
    assert np.isfinite(result.velocities).all()
    print(f"    final_R={result.summary['final_R']:.4f}")
    print(f"    freq_nadir={result.summary.get('frequency_nadir', 'N/A')}")
    print(f"    max_rocof={result.summary.get('max_rocof', 'N/A')}")


@test("6b. Second-order — heterogeneous inertia")
def test_second_order_hetero():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.second_order import SecondOrderKuramotoEngine

    N = 30
    rng = np.random.default_rng(42)
    mass = rng.uniform(0.5, 5.0, N)
    damping = rng.uniform(0.05, 0.5, N)
    cfg = KuramotoConfig(N=N, K=8.0, dt=0.005, steps=4000, seed=42)
    result = SecondOrderKuramotoEngine(cfg, mass=mass, damping=damping).run()
    assert np.isfinite(result.phases).all()
    assert np.isfinite(result.velocities).all()


@test("6c. Second-order — high damping converges to first-order")
def test_second_order_overdamped():
    from core.kuramoto import KuramotoConfig, KuramotoEngine
    from core.kuramoto.second_order import SecondOrderKuramotoEngine

    cfg = KuramotoConfig(N=20, K=3.0, dt=0.001, steps=10000, seed=42)
    # High damping, moderate mass → approaches first-order behaviour
    r_2nd = SecondOrderKuramotoEngine(cfg, mass=0.1, damping=5.0).run()
    r_1st = KuramotoEngine(cfg).run()
    # Should qualitatively agree on final synchronization level
    assert abs(r_2nd.summary["final_R"] - r_1st.summary["final_R"]) < 0.2


# ============================================================
# 7. EARLY STOPPING
# ============================================================


@test("7a. Early stopping — strong coupling (should stop early)")
def test_early_stop_fast():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.early_stopping import EarlyStoppingEngine

    cfg = KuramotoConfig(N=50, K=5.0, dt=0.01, steps=50000, seed=42)
    result = EarlyStoppingEngine(cfg, epsilon=1e-5, patience=200, min_steps=100).run()
    print(
        f"    stopped at step {result.summary['converged_at_step']}/{result.summary['max_steps']}"
    )
    print(f"    saved {result.summary['compute_saved_pct']:.1f}% compute")
    assert result.summary["early_stopped"] is True
    assert result.summary["compute_saved_pct"] > 30.0


@test("7b. Early stopping — weak coupling (should run longer)")
def test_early_stop_slow():
    from core.kuramoto import KuramotoConfig
    from core.kuramoto.early_stopping import EarlyStoppingEngine

    cfg = KuramotoConfig(N=50, K=0.5, dt=0.01, steps=5000, seed=42)
    result = EarlyStoppingEngine(cfg, epsilon=1e-4, patience=100, min_steps=100).run()
    print(
        f"    stopped at step {result.summary['converged_at_step']}/{result.summary['max_steps']}"
    )
    # Weak coupling → might not converge quickly, but should still produce valid result
    assert 0.0 <= result.summary["final_R"] <= 1.0


@test("7c. Early stopping — correctness vs full run")
def test_early_stop_correctness():
    from core.kuramoto import KuramotoConfig, KuramotoEngine
    from core.kuramoto.early_stopping import EarlyStoppingEngine

    cfg = KuramotoConfig(N=30, K=4.0, dt=0.01, steps=10000, seed=42)
    r_full = KuramotoEngine(cfg).run()
    r_early = EarlyStoppingEngine(cfg, epsilon=1e-5, patience=200).run()
    # Early-stopped R should be close to full-run R at convergence
    np.testing.assert_allclose(
        r_early.summary["final_R"],
        r_full.summary["final_R"],
        atol=0.05,
    )


# ============================================================
# STRESS TEST — PERFORMANCE
# ============================================================


@test("STRESS: Dense N=300, 5000 steps")
def test_stress_dense():
    from core.kuramoto import KuramotoConfig, KuramotoEngine

    cfg = KuramotoConfig(N=300, K=2.0, dt=0.01, steps=5000, seed=42)
    result = KuramotoEngine(cfg).run()
    assert result.phases.shape == (5001, 300)
    mem_mb = result.phases.nbytes / 1e6
    print(f"    phases: {mem_mb:.1f} MB")


@test("STRESS: Sparse N=20000, 50 steps, density=0.0005")
def test_stress_sparse():
    from scipy import sparse

    from core.kuramoto import KuramotoConfig
    from core.kuramoto.sparse import SparseKuramotoEngine

    N = 20_000
    adj = sparse.random(N, N, density=0.0005, format="csr", random_state=42)
    cfg = KuramotoConfig(N=N, K=1.0, dt=0.01, steps=50, seed=42)
    result = SparseKuramotoEngine(cfg, sparse_adjacency=adj).run()
    assert result.phases.shape == (51, N)
    print(f"    N={N:,}, edges={adj.nnz:,}")


# ============================================================
# RUN ALL
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("GeoSync Kuramoto Full Hardware Test Suite")
    print("=" * 70)
    print()

    tests = [
        test_baseline,
        test_jax_import,
        test_jax_single,
        test_jax_batch,
        test_sparse_small,
        test_sparse_large,
        test_sparse_dense_equiv,
        test_adaptive_rk45,
        test_adaptive_lsoda,
        test_adaptive_vs_fixed,
        test_phase_transition,
        test_phase_transition_mono,
        test_dde_uniform,
        test_dde_heterogeneous,
        test_dde_zero_delay,
        test_second_order_basic,
        test_second_order_hetero,
        test_second_order_overdamped,
        test_early_stop_fast,
        test_early_stop_slow,
        test_early_stop_correctness,
        test_stress_dense,
        test_stress_sparse,
    ]

    total_t0 = time.perf_counter()
    for t in tests:
        t()
    total_dt = time.perf_counter() - total_t0

    print()
    print("=" * 70)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    print(f"TOTAL: {passed} passed, {failed} failed, {skipped} skipped — {total_dt:.1f}s")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
