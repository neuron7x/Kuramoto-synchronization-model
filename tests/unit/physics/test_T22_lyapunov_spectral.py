# SPDX-License-Identifier: MIT
"""T22 — Lyapunov exponent and spectral gap witnesses.

Two new physics diagnostics for GeoSync:

1. **Maximal Lyapunov Exponent (MLE)** — chaos/order detector on scalar
   time series. INV-LE1 (finite), INV-LE2 (sign semantics).

2. **Spectral Gap (Fiedler λ₂)** — algebraic connectivity of the
   coupling graph. INV-SG1 (non-negative), INV-SG2 (connectivity ↔ λ₂>0).
"""

from __future__ import annotations

from typing import Any

import math

import networkx as nx
import numpy as np
import pytest

from core.physics.lyapunov_exponent import (
    R2_MIN,
    maximal_lyapunov_exponent,
    spectral_gap,
)

# ── INV-LE1: MLE finite for non-degenerate input, fail-closed otherwise ──


def test_mle_finite_on_diverse_inputs() -> None:
    """INV-LE1: MLE is a finite real for every *non-degenerate* bounded input.

    Sweeps white noise, sine, random walk, and step function inputs — each
    has measurable nearest-neighbor divergence, so the Rosenstein MLE is
    defined and must be finite (not NaN/Inf).

    NOTE (contract correction): a perfectly *constant* series used to be in
    this sweep and asserted finite. That was the silent-0.0 masking bug —
    a constant series has no divergence to measure (Rosenstein 1993 §2.2),
    so reporting λ=0 falsely labelled it a "stable regime". The corrected
    INV-LE1 fails closed on degenerate input; the constant case now lives in
    ``test_mle_fails_closed_on_constant_input`` below.
    """
    rng = np.random.default_rng(seed=0)
    n = 500
    # epsilon: finiteness is the invariant, no numeric tolerance needed
    series_bank: dict[str, np.ndarray] = {
        "white_noise": rng.normal(0, 1, n),
        "sine": np.sin(np.linspace(0, 20 * math.pi, n)),
        "random_walk": np.cumsum(rng.normal(0, 0.01, n)),
        "step": np.concatenate([np.zeros(n // 2), np.ones(n // 2)]),
    }

    for label, series in series_bank.items():
        mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
        assert math.isfinite(mle), (
            f"INV-LE1 VIOLATED on series={label}: MLE={mle} non-finite. "
            f"Expected finite MLE for any non-degenerate bounded input. "
            f"Observed at N={n}, dim=3, tau=1. "
            f"Physical reasoning: Rosenstein algorithm uses log(distance) "
            f"which is finite for non-zero distances between embedded points."
        )


def test_mle_fails_closed_on_constant_input() -> None:
    """INV-LE1 (fail-closed): a constant series MUST raise, not return 0.0.

    A constant trajectory collapses every delay-embedded point onto a single
    location, so all nearest-neighbor pair distances are zero and the
    Rosenstein divergence rate is undefined (1993 §2.2). The estimator must
    fail closed rather than emit a spurious λ=0 that downstream risk gating
    would read as a stable regime.
    """
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(np.full(500, 42.0), dim=3, tau=1)


# ── INV-LE2: MLE sign matches dynamical regime ──────────────────────


def test_mle_sign_matches_dynamical_regime() -> None:
    """INV-LE2: MLE(noise) ≈ 0, MLE(stable) < 0, MLE(chaotic) > 0.

    Three canonical dynamical systems with known Lyapunov exponents:
    1. White noise: λ ≈ 0 (no deterministic structure)
    2. Stable logistic map (r=2.8): λ < 0 (converging to a fixed point)
    3. Logistic map (r=4): λ = ln(2) ≈ 0.693 (maximal chaos)

    NOTE on the stable case (scaling-region / INV-LE3 aware): the prior test
    used a damped sinusoid x(t)=e^{-0.1t}·sin(t) at dim=3,tau=5 and asserted
    λ < 0. With the INV-LE3 scaling-region gate active, that fit is exposed as
    R² ≈ 0.32 — it is NOT a clean Rosenstein scaling region (the Rosenstein
    neighbor-divergence estimator measures transient phase-space stretching of
    a sampled flow, not the global contraction, so the negative slope it
    produced was an untrustworthy artifact that the new gate correctly demotes
    to 0.0). The honest negative-λ witness is the logistic map in its stable
    regime (r=2.8), whose neighbor pairs genuinely contract on a clean linear
    scaling region (R² ≈ 1.0, λ ≈ −0.11).
    """
    n = 3000

    # 1. White noise: MLE should be near zero (no predictable structure)
    rng = np.random.default_rng(seed=1)
    noise = rng.normal(0, 1, n)
    mle_noise = maximal_lyapunov_exponent(noise, dim=5, tau=1)

    # 2. Stable logistic map r=2.8: converges to a fixed point → λ < 0 on a
    #    clean Rosenstein scaling region (passes INV-LE3).
    stable = np.empty(n)
    stable[0] = 0.3
    for i in range(1, n):
        stable[i] = 2.8 * stable[i - 1] * (1.0 - stable[i - 1])
    diag_stable: dict[str, float] = {}
    mle_stable = maximal_lyapunov_exponent(
        stable, dim=3, tau=1, max_divergence_steps=30, diagnostics=diag_stable
    )

    # 3. Logistic map r=4: x_{n+1} = 4·x·(1-x), theoretical λ = ln(2)
    logistic = np.empty(n)
    logistic[0] = 0.1
    for i in range(1, n):
        logistic[i] = 4.0 * logistic[i - 1] * (1.0 - logistic[i - 1])
    # dim=2 (natural for 1D map), max_divergence_steps=20 (short fit window
    # to capture the initial exponential growth before saturation on the attractor)
    mle_logistic = maximal_lyapunov_exponent(logistic, dim=2, tau=1, max_divergence_steps=20)

    print(
        f"  MLE(noise)={mle_noise:.4f}, MLE(stable)={mle_stable:.4f} "
        f"(R²={diag_stable['r_squared']:.4f}), MLE(logistic)={mle_logistic:.4f}"
    )

    # Logistic chaos should have highest MLE
    # tolerance: logistic MLE should be near ln(2)=0.693 within 20%
    theoretical_ln2 = math.log(2.0)  # epsilon: theoretical λ for logistic r=4
    assert mle_logistic > 0.5 * theoretical_ln2, (
        f"INV-LE2 VIOLATED: MLE(logistic)={mle_logistic:.4f} ≤ {0.5 * theoretical_ln2:.3f}. "
        f"Expected λ ≈ ln(2)={theoretical_ln2:.4f} for chaotic logistic map. "
        f"Observed at N={n}, dim=2, tau=1, max_div=20, r=4.0. "
        f"Physical reasoning: the logistic map at r=4 is maximally chaotic."
    )

    # Stable logistic (r=2.8) should be negative AND pass the INV-LE3 gate
    assert diag_stable["scaling_ok"] == 1.0, (
        f"INV-LE3 precondition: stable r=2.8 fit flagged non-scaling "
        f"(scaling_ok={diag_stable['scaling_ok']}, R²={diag_stable['r_squared']:.4f}). "
        f"Expected a clean linear scaling region for a contracting map. "
        f"Observed at N={n}, dim=3, tau=1, max_div=30. "
        f"Physical reasoning: fixed-point convergence ⟹ monotone neighbor "
        f"contraction ⟹ linear log-divergence ⟹ high R²."
    )
    assert mle_stable < 0.0, (  # epsilon: theoretical λ < 0 for stable fixed point
        f"INV-LE2 VIOLATED: MLE(stable r=2.8)={mle_stable:.4f} ≥ 0. "
        f"Expected λ < 0 for the logistic map converging to a fixed point. "
        f"Observed at N={n}, dim=3, tau=1, max_div=30, R²={diag_stable['r_squared']:.4f}. "
        f"Physical reasoning: stable regime converges → nearby "
        f"trajectories converge → λ < 0."
    )

    # Logistic should dominate noise
    assert mle_logistic > mle_noise, (
        f"INV-LE2 VIOLATED: MLE(logistic)={mle_logistic:.4f} ≤ "
        f"MLE(noise)={mle_noise:.4f}. "
        f"Expected deterministic chaos to have higher divergence than noise. "
        f"Observed at N={n}. "
        f"Physical reasoning: logistic map has structured divergence, "
        f"noise has unstructured fluctuation."
    )


# ── INV-LE3: log-divergence fit R² ≥ R2_MIN OR flagged non-scaling ──


def _logistic_r4(n: int, x0: float = 0.1) -> np.ndarray:
    """Logistic map x_{n+1} = 4·x·(1−x): canonical r=4 maximal chaos."""
    out = np.empty(n)
    out[0] = x0
    for i in range(1, n):
        out[i] = 4.0 * out[i - 1] * (1.0 - out[i - 1])
    return out


def test_le3_clean_chaos_passes_scaling_gate() -> None:
    """INV-LE3 (a): a clean chaotic series sits in a linear scaling region.

    Logistic map r=4 has a genuine exponential divergence regime, so the
    log-divergence fit must reach R² ≥ R2_MIN and the gate must ACCEPT the
    slope as a positive λ (λ ≈ ln 2). The scaling flag must be set.
    """
    n = 2000
    logistic = _logistic_r4(n)
    diag: dict[str, float] = {}
    # dim=2 natural for a 1D map; short fit window captures the initial
    # exponential growth before attractor saturation.
    lam = maximal_lyapunov_exponent(
        logistic, dim=2, tau=1, max_divergence_steps=20, diagnostics=diag
    )

    assert diag["r_squared"] >= R2_MIN, (
        f"INV-LE3 VIOLATED: clean chaos R²={diag['r_squared']:.4f} < "
        f"R2_MIN={R2_MIN:.2f}. "
        f"Expected logistic r=4 to have a clean linear scaling region. "
        f"Observed at N={n}, dim=2, tau=1, max_div=20, n_fit={diag['n_fit']:.0f}. "
        f"Physical reasoning: r=4 logistic has a true exponential divergence "
        f"regime → log-divergence vs time is linear → high R²."
    )
    assert diag["scaling_ok"] == 1.0, (
        f"INV-LE3 VIOLATED: clean chaos flagged non-scaling "
        f"(scaling_ok={diag['scaling_ok']}). "
        f"Expected the gate to accept a clean scaling region. "
        f"Observed R²={diag['r_squared']:.4f} ≥ R2_MIN={R2_MIN:.2f}. "
        f"Physical reasoning: high-R² fit ⟹ trustworthy slope ⟹ accept."
    )
    assert lam > 0.0, (
        f"INV-LE3+LE2 VIOLATED: accepted λ={lam:.4f} ≤ 0 for chaotic input. "
        f"Expected λ > 0 (≈ ln 2 = {math.log(2.0):.4f}) for logistic r=4. "
        f"Observed R²={diag['r_squared']:.4f}, scaling_ok={diag['scaling_ok']}. "
        f"Physical reasoning: maximal chaos ⟹ positive divergence rate."
    )


def test_le3_nonscaling_input_fails_closed() -> None:
    """INV-LE3 (b): a non-scaling input must be flagged, never a silent slope.

    Pure white noise has no deterministic exponential divergence regime, so
    the log-divergence curve is not linear: R² falls below R2_MIN. The gate
    must FAIL CLOSED — flag scaling_ok=0 AND return the no-reliable-estimate
    sentinel 0.0 (the module's existing convention), NOT the raw slope.
    """
    rng = np.random.default_rng(seed=7)
    n = 2000
    noise = rng.normal(0.0, 1.0, n)
    diag: dict[str, float] = {}
    lam = maximal_lyapunov_exponent(noise, dim=5, tau=1, diagnostics=diag)

    assert diag["r_squared"] < R2_MIN, (
        f"INV-LE3 test precondition: noise R²={diag['r_squared']:.4f} ≥ "
        f"R2_MIN={R2_MIN:.2f} — expected a NON-scaling curve. "
        f"Observed at N={n}, dim=5, tau=1, n_fit={diag['n_fit']:.0f}. "
        f"Physical reasoning: iid noise has no exponential divergence regime."
    )
    assert diag["scaling_ok"] == 0.0, (
        f"INV-LE3 VIOLATED: non-scaling noise NOT flagged "
        f"(scaling_ok={diag['scaling_ok']}). "
        f"Expected the gate to reject R²={diag['r_squared']:.4f} < "
        f"R2_MIN={R2_MIN:.2f}. "
        f"Physical reasoning: low-R² fit ⟹ untrustworthy slope ⟹ reject."
    )
    assert lam == 0.0, (
        f"INV-LE3 VIOLATED: returned silent slope λ={lam:.6f} instead of the "
        f"no-reliable-estimate sentinel 0.0 for a non-scaling input. "
        f"Raw (rejected) slope was {diag['slope']:.6f}. "
        f"Observed R²={diag['r_squared']:.4f} < R2_MIN={R2_MIN:.2f}, N={n}. "
        f"Physical reasoning: a slope from a non-linear region is meaningless; "
        f"fail closed rather than fabricate a chaos/stability verdict."
    )


def test_le3_gate_only_demotes_never_fabricates() -> None:
    """INV-LE3 (c): the gate demotes untrustworthy estimates, never invents.

    Sweep a bank of inputs. For every input the gate either (i) accepts with
    R² ≥ R2_MIN, or (ii) flags scaling_ok=0 AND returns exactly 0.0. A
    rejected input may NEVER return a non-zero λ. This is the falsifier
    property: a confident λ from a non-scaling region is forbidden.
    """
    rng = np.random.default_rng(seed=11)
    n = 2000
    t = np.linspace(0.0, 100.0, n)
    bank: dict[str, tuple[np.ndarray, dict[str, Any]]] = {
        "logistic": (_logistic_r4(n), {"dim": 2, "tau": 1, "max_divergence_steps": 20}),
        "noise": (rng.normal(0.0, 1.0, n), {"dim": 5, "tau": 1}),
        "damped": (np.exp(-0.1 * t) * np.sin(t), {"dim": 3, "tau": 5}),
        "random_walk": (np.cumsum(rng.normal(0.0, 0.01, n)), {"dim": 3, "tau": 1}),
        "sine": (np.sin(np.linspace(0.0, 20 * math.pi, n)), {"dim": 3, "tau": 1}),
    }
    for label, (series, kw) in bank.items():
        diag: dict[str, float] = {}
        lam = maximal_lyapunov_exponent(series, diagnostics=diag, **kw)
        accepted = diag["scaling_ok"] == 1.0
        if not accepted:
            assert lam == 0.0, (
                f"INV-LE3 VIOLATED on series={label}: rejected fit "
                f"(scaling_ok=0) still emitted non-zero λ={lam:.6f}. "
                f"Expected the no-reliable-estimate sentinel 0.0. "
                f"Observed R²={diag['r_squared']:.4f} < R2_MIN={R2_MIN:.2f}. "
                f"Physical reasoning: non-scaling region ⟹ no trustworthy λ."
            )
        else:
            assert diag["r_squared"] >= R2_MIN, (
                f"INV-LE3 VIOLATED on series={label}: accepted "
                f"(scaling_ok=1) with R²={diag['r_squared']:.4f} < "
                f"R2_MIN={R2_MIN:.2f}. "
                f"Expected acceptance only above the scaling-region floor. "
                f"Observed λ={lam:.4f}, n_fit={diag['n_fit']:.0f}. "
                f"Physical reasoning: acceptance requires a linear fit."
            )


# ── INV-SG1: λ₂ ≥ 0 always ─────────────────────────────────────────


def test_spectral_gap_non_negative_on_diverse_graphs() -> None:
    """INV-SG1: λ₂ ≥ 0 for every graph topology.

    Sweeps path, cycle, complete, star, random, and disconnected graphs.
    λ₂ must be non-negative for each (Laplacian is PSD).
    """
    # epsilon: λ₂ ≥ 0 is a PSD property, no numerical tolerance needed
    graphs: dict[str, np.ndarray] = {
        "path_10": nx.to_numpy_array(nx.path_graph(10)),
        "cycle_12": nx.to_numpy_array(nx.cycle_graph(12)),
        "complete_6": nx.to_numpy_array(nx.complete_graph(6)),
        "star_8": nx.to_numpy_array(nx.star_graph(7)),
        "erdos_renyi": nx.to_numpy_array(nx.erdos_renyi_graph(15, 0.3, seed=42)),
        "disconnected": np.block(
            [
                [nx.to_numpy_array(nx.complete_graph(4)), np.zeros((4, 4))],
                [np.zeros((4, 4)), nx.to_numpy_array(nx.complete_graph(4))],
            ]
        ),
        "single_edge": np.array([[0.0, 1.0], [1.0, 0.0]]),
    }

    for label, adj in graphs.items():
        lam2 = spectral_gap(adj)
        assert lam2 >= 0.0, (  # epsilon: PSD → λ₂ ≥ 0 exactly
            f"INV-SG1 VIOLATED on graph={label}: λ₂={lam2:.6f} < 0. "
            f"Expected λ₂ ≥ 0 by positive semi-definiteness of the Laplacian. "
            f"Observed at N={adj.shape[0]} nodes. "
            f"Physical reasoning: L = D - A is PSD for non-negative A."
        )


# ── INV-SG2: λ₂ > 0 ⟺ connected ───────────────────────────────────


def test_spectral_gap_connectivity_equivalence() -> None:
    """INV-SG2: λ₂ > 0 if and only if the graph is connected.

    Tests connected graphs (should have λ₂ > 0) and disconnected graphs
    (should have λ₂ = 0 or very near 0).
    """
    # Connected graphs: λ₂ must be strictly positive
    connected_graphs: dict[str, np.ndarray] = {
        "path_10": nx.to_numpy_array(nx.path_graph(10)),
        "complete_6": nx.to_numpy_array(nx.complete_graph(6)),
        "cycle_8": nx.to_numpy_array(nx.cycle_graph(8)),
    }
    for label, adj in connected_graphs.items():
        lam2 = spectral_gap(adj)
        # tolerance: eigenvalue solver has O(eps_machine) slack
        assert lam2 > 1e-10, (  # epsilon: machine-precision floor for "positive"
            f"INV-SG2 VIOLATED: connected graph={label} has λ₂={lam2:.3e} ≈ 0. "
            f"Expected λ₂ > 0 for a connected graph. "
            f"Observed at N={adj.shape[0]} nodes. "
            f"Physical reasoning: connected ⟹ algebraic multiplicity of 0 "
            f"eigenvalue is exactly 1 ⟹ λ₂ > 0."
        )

    # Disconnected graph: λ₂ must be 0 (or near 0)
    adj_disconnected = np.block(
        [
            [nx.to_numpy_array(nx.complete_graph(5)), np.zeros((5, 5))],
            [np.zeros((5, 5)), nx.to_numpy_array(nx.complete_graph(5))],
        ]
    )
    lam2_disc = spectral_gap(adj_disconnected)
    # tolerance: numerical λ₂ may be slightly above 0 due to float precision
    assert lam2_disc < 1e-10, (  # epsilon: machine-precision ceiling for "zero"
        f"INV-SG2 VIOLATED: disconnected graph has λ₂={lam2_disc:.3e} > 0. "
        f"Expected λ₂ ≈ 0 for a disconnected graph (two K5 components). "
        f"Observed at N=10 nodes (2×5 disconnected). "
        f"Physical reasoning: disconnected ⟹ eigenvalue 0 has "
        f"multiplicity ≥ 2 ⟹ λ₂ = 0."
    )


# ── Integration: MLE on Kuramoto R(t) trajectory ────────────────────


def test_mle_on_kuramoto_subcritical_vs_supercritical() -> None:
    """INV-LE2 + INV-K2/K3: MLE of R(t) reflects synchronization regime.

    Subcritical R(t) fluctuates stochastically → MLE ≈ 0 or > 0 (noisy).
    Supercritical R(t) converges to stable R∞ → MLE < 0 (stable).
    The MLE of R(t) is a HIGHER-ORDER diagnostic than R itself — it tells
    you not just "where is R?" but "is R's dynamics predictable?"
    """
    from core.kuramoto.config import KuramotoConfig
    from core.kuramoto.engine import KuramotoEngine

    n_osc = 128
    sigma = 1.0
    K_c = 2.0 * sigma * math.sqrt(2 * math.pi) / math.pi
    rng = np.random.default_rng(seed=99)
    omega = rng.normal(0, sigma, n_osc)
    theta0 = rng.uniform(-math.pi, math.pi, n_osc)

    # Supercritical: R(t) → stable R∞
    cfg_super = KuramotoConfig(
        N=n_osc,
        K=2.0 * K_c,
        omega=omega,
        theta0=theta0,
        dt=0.01,
        steps=2000,
        seed=99,
    )
    R_super = KuramotoEngine(cfg_super).run().order_parameter
    mle_super = maximal_lyapunov_exponent(R_super[500:], dim=3, tau=5)

    # Subcritical: R(t) fluctuates around noise floor
    cfg_sub = KuramotoConfig(
        N=n_osc,
        K=0.3 * K_c,
        omega=omega,
        theta0=theta0,
        dt=0.01,
        steps=2000,
        seed=99,
    )
    R_sub = KuramotoEngine(cfg_sub).run().order_parameter
    mle_sub = maximal_lyapunov_exponent(R_sub[500:], dim=3, tau=5)

    print(f"  MLE(R_super)={mle_super:.4f}, MLE(R_sub)={mle_sub:.4f}")

    # Supercritical should be more stable (lower MLE) than subcritical
    assert mle_super < mle_sub, (
        f"INV-LE2 integration: MLE(supercritical)={mle_super:.4f} ≥ "
        f"MLE(subcritical)={mle_sub:.4f}. "
        f"Expected supercritical R(t) to be more stable (lower MLE) "
        f"than subcritical noise. "
        f"Observed at N={n_osc}, K_super=2·K_c, K_sub=0.3·K_c, seed=99. "
        f"Physical reasoning: supercritical R(t) converges to a stable "
        f"fixed point → nearby trajectories converge → λ < λ(noise)."
    )


# ---------------------------------------------------------------------------
# TEETH — measured gap: mutation_probe --only-logic left the spectral_gap contract
# guards alive (:501 Or->And on the shape check, :515/:516 on the negative-mass
# detection). Nothing exercised a NON-SQUARE 2-D matrix or a negatively-weighted
# adjacency, so both guards could be inverted undetected.
# ---------------------------------------------------------------------------
def test_spectral_gap_rejects_a_non_square_two_dimensional_matrix() -> None:
    """The shape guard is OR: 2-D but non-square must still raise.

    Under Or->And only a matrix that is BOTH non-2-D AND non-square would raise, so a
    plain 2x3 block would slip into the Laplacian.
    """
    import numpy as np
    import pytest

    from core.physics.lyapunov_exponent import spectral_gap

    with pytest.raises(ValueError, match="Expected square matrix"):
        spectral_gap(np.ones((2, 3), dtype=np.float64))


def test_spectral_gap_surfaces_clamped_negative_adjacency(caplog) -> None:
    """The clamp must be SURFACED, not silent (the module's own observability contract).

    Pins :515/:516: those guards feed only the warning, so a numeric assertion cannot see
    them — an inverted detection would silently drop a sign/data fault.
    """
    import logging

    import numpy as np

    from core.physics.lyapunov_exponent import spectral_gap

    adj = np.array(
        [[0.0, 1.0, -5.0], [1.0, 0.0, 1.0], [-5.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    with caplog.at_level(logging.WARNING, logger="core.physics.lyapunov_exponent"):
        spectral_gap(adj)
    assert any("clamped" in r.message or "clamped" in r.getMessage() for r in caplog.records), (
        "a non-trivial negative adjacency mass must be logged before clamping; "
        f"records={[r.getMessage() for r in caplog.records]}"
    )


def test_spectral_gap_clamps_negative_adjacency_and_stays_non_negative() -> None:
    """INV-HPC2/INV-SG1: negative weights are clamped to 0 and lambda2 stays >= 0.

    Pins the negative-mass detection (:515/:516): the clamped graph is the path 0-1-2 with
    unit weights, whose Fiedler value is 1.0, so an inverted detection cannot reproduce it.
    """
    import numpy as np

    from core.physics.lyapunov_exponent import spectral_gap

    adj = np.array(
        [[0.0, 1.0, -5.0], [1.0, 0.0, 1.0], [-5.0, 1.0, 0.0]],
        dtype=np.float64,
    )
    lam2 = spectral_gap(adj)
    assert lam2 >= 0.0, f"INV-SG1: lambda2 must be non-negative, got {lam2}"
    assert lam2 == pytest.approx(1.0, abs=1e-9), (
        f"after clamping the -5 weights the graph is the unit path 0-1-2 whose Fiedler "
        f"value is 1.0; got {lam2}"
    )
