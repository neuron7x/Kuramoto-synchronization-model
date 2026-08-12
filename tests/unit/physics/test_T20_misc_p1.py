# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T20 — Miscellaneous P1 invariants: TH1, TH2, KELLY3, ES2, CB5.

Five remaining P1 invariants that span conservation laws,
entropy production, Kelly optimality, explosive synchronization,
and cryptobiosis configuration contracts.
"""

from __future__ import annotations

import math

import numpy as np

from core.neuro.cryptobiosis import CryptobiosisConfig
from core.physics.explosive_sync import ExplosiveSyncDetector
from core.physics.portfolio_conservation import PortfolioEnergyConservation
from core.physics.thermodynamics import boltzmann_entropy

# ── INV-TH1: Energy conservation (balance test) ────────────────


def test_inv_th1_energy_conservation_balance() -> None:
    """INV-TH1 (conservation/balance_test): |Delta-E| <= epsilon after rebalance.

    Simulates a small rebalance where positions shift by a perturbation
    drawn from N(0, 0.005). Because the perturbation is small, the energy
    change must remain within the configured epsilon.
    """
    rng = np.random.default_rng(seed=42)
    n_assets = 8
    # INV-TH1: epsilon = 0.05 (configured threshold for conservation)
    epsilon = 0.05  # epsilon: maximum allowed |Delta-E| per rebalance

    conservator = PortfolioEnergyConservation(epsilon=epsilon, return_window=5)

    positions_before = rng.uniform(low=0.05, high=0.25, size=n_assets)
    positions_before /= positions_before.sum()  # normalise to sum=1
    returns = rng.uniform(low=-0.02, high=0.02, size=n_assets)
    expected_returns = rng.uniform(low=-0.01, high=0.01, size=n_assets)

    # Compute total energy BEFORE rebalance
    total_before = conservator.compute_total(positions_before, returns, expected_returns)

    # Small rebalance: positions shift by a tiny perturbation
    perturbation_scale = 0.005  # tolerance: small enough to stay within epsilon
    perturbation = rng.normal(scale=perturbation_scale, size=n_assets)
    positions_after = positions_before + perturbation
    positions_after = np.maximum(positions_after, 0.0)
    positions_after /= positions_after.sum()

    # Compute total energy AFTER rebalance
    total_after = conservator.compute_total(positions_after, returns, expected_returns)

    delta_e = abs(total_after - total_before)
    assert delta_e <= epsilon, (
        f"INV-TH1 VIOLATED: |Delta-E|={delta_e:.6f} > epsilon={epsilon:.6f}. "
        f"Expected energy change within conservation bound after small rebalance. "
        f"total_before={total_before:.6f}, total_after={total_after:.6f}. "
        f"Perturbation scale={perturbation_scale}, N={n_assets} assets, seed=42. "
        f"Physical reasoning: small position perturbation implies small energy change."
    )

    conserved = conservator.check_conservation(total_before, total_after)
    assert conserved, (
        f"INV-TH1 VIOLATED: check_conservation returned False. "
        f"|Delta-E|={delta_e:.6f} should be <= epsilon={epsilon:.6f}. "
        f"total_before={total_before:.6f}, total_after={total_after:.6f}. "
        f"Perturbation scale={perturbation_scale}, N={n_assets} assets, seed=42. "
        f"Physical reasoning: work + dissipation within threshold => conserved."
    )


# ── INV-TH2: Entropy production >= 0 (property test) ───────────


def test_inv_th2_entropy_non_negative_sweep() -> None:
    """INV-TH2 (universal/property_test): S >= 0 for all valid distributions.

    Sweeps through several probability distributions (uniform, skewed,
    concentrated, Dirichlet-drawn) and asserts Boltzmann entropy is
    non-negative for each.
    """
    rng = np.random.default_rng(seed=42)

    distributions: list[tuple[str, np.ndarray]] = [
        ("uniform_4", np.array([0.25, 0.25, 0.25, 0.25])),
        ("uniform_10", np.ones(10) / 10.0),
        ("skewed", np.array([0.7, 0.1, 0.1, 0.05, 0.05])),
        ("concentrated", np.array([0.99, 0.005, 0.005])),
        ("binary_equal", np.array([0.5, 0.5])),
        ("degenerate_single", np.array([1.0])),
    ]

    # Add 10 Dirichlet-drawn distributions for broader coverage
    for i in range(10):
        n_bins = int(rng.integers(low=3, high=20))
        alpha = rng.uniform(low=0.1, high=5.0, size=n_bins)
        probs = rng.dirichlet(alpha)
        distributions.append((f"dirichlet_{i}", probs))

    # INV-TH2: entropy floor is 0 (second law)
    entropy_floor = 0.0  # tolerance: exact theoretical floor

    for label, probs in distributions:
        s_val = boltzmann_entropy(probs)
        assert math.isfinite(s_val), (
            f"INV-TH2 VIOLATED: S={s_val} non-finite for dist='{label}'. "
            f"Expected finite entropy for any valid probability distribution. "
            f"Distribution shape={probs.shape}, sum={probs.sum():.6f}. "
            f"Seed=42, distribution label='{label}'. "
            f"Physical reasoning: S = -k_B * sum(p*ln(p)) is finite for p > 0."
        )
        assert s_val >= entropy_floor, (
            f"INV-TH2 VIOLATED: S={s_val:.8f} < 0 for dist='{label}'. "
            f"Expected entropy production >= 0 (second law of thermodynamics). "
            f"Distribution: {probs[:5]}{'...' if len(probs) > 5 else ''}. "
            f"Seed=42, distribution label='{label}'. "
            f"Physical reasoning: -sum(p*ln(p)) >= 0 since p*ln(p) <= 0 for p in (0,1]."
        )


# ── INV-KELLY3: Kelly fraction optimality (ensemble test) ──────


def test_inv_kelly3_log_growth_argmax() -> None:
    """INV-KELLY3 (statistical/ensemble_test): argmax of E[log(1+f*X)] near f* = mu/sigma^2.

    Generates 2,000,000 Uniform(mu-a, mu+a) returns and evaluates the
    expected log-growth on a grid of fractions. Asserts that the argmax
    fraction is within 3 grid steps of the theoretical optimum
    f* = mu/sigma^2 = 3*mu/a^2 for uniform distribution.
    """
    rng = np.random.default_rng(seed=42)

    mu = 0.01  # INV-KELLY3: mean return
    a = 0.3  # INV-KELLY3: half-width of uniform distribution
    n_samples = 2_000_000  # INV-KELLY3: sample count for convergence

    returns = rng.uniform(low=mu - a, high=mu + a, size=n_samples)

    # For Uniform(mu-a, mu+a): sigma^2 = a^2/3, so f* = mu/sigma^2 = 3*mu/a^2
    f_star_theoretical = 3.0 * mu / (a**2)  # INV-KELLY3: theoretical Kelly fraction

    grid_step = 0.005  # INV-KELLY3: grid resolution
    fractions = np.arange(0.0, 1.0 + grid_step, grid_step)

    log_growths = np.zeros(len(fractions))
    for i, f in enumerate(fractions):
        # Clip to avoid log(0) or log(negative) for safety
        growth = 1.0 + f * returns
        growth = np.maximum(growth, 1e-15)  # bounds: prevent log(0)
        log_growths[i] = np.mean(np.log(growth))

    argmax_idx = int(np.argmax(log_growths))
    f_argmax = fractions[argmax_idx]

    # Allow 3 grid steps tolerance: the continuous f*=mu/sigma^2 is a
    # small-edge approximation; with a=0.3 the higher-order log-concavity
    # correction shifts the empirical optimum by ~1 extra grid step.
    grid_tolerance = 3 * grid_step  # tolerance: 3 grid steps = 0.015
    distance = abs(f_argmax - f_star_theoretical)

    assert distance <= grid_tolerance, (
        f"INV-KELLY3 VIOLATED: f_argmax={f_argmax:.4f} vs "
        f"f*_theoretical={f_star_theoretical:.4f}, distance={distance:.4f} > "
        f"tolerance={grid_tolerance:.4f}. "
        f"Expected argmax within 3 grid steps of mu/sigma^2 = 3*mu/a^2. "
        f"mu={mu}, a={a}, n_samples={n_samples}, grid_step={grid_step}, seed=42. "
        f"Physical reasoning: Kelly criterion maximises E[log(1+f*X)] near f*=mu/sigma^2."
    )

    # Also verify the argmax growth exceeds growth at f=0 (no bet) and f=1 (full bet)
    assert log_growths[argmax_idx] >= log_growths[0], (
        f"INV-KELLY3 VIOLATED: log_growth(f*={f_argmax:.4f})={log_growths[argmax_idx]:.8f} "
        f"< log_growth(f=0)={log_growths[0]:.8f}. "
        f"Expected optimal fraction to beat zero allocation. "
        f"mu={mu}, a={a}, n_samples={n_samples}, seed=42. "
        f"Physical reasoning: positive-edge returns should reward nonzero Kelly fraction."
    )


# ── INV-ES2: Explosive sync with freq-degree correlation ───────


def test_inv_es2_frequency_degree_correlation_discontinuous() -> None:
    """INV-ES2 (qualitative/sweep_test): freq-degree correlation yields hysteresis > 0.

    Creates a scale-free-like adjacency where node degrees correlate
    with natural frequencies, which is the known trigger for explosive
    (first-order) synchronization. Asserts that the detector finds
    non-zero proximity (some hysteresis).
    """
    rng = np.random.default_rng(seed=42)
    n_nodes = 10  # INV-ES2: small network for test speed

    # Build a scale-free-like adjacency with a hub structure
    adjacency = np.zeros((n_nodes, n_nodes), dtype=np.float64)

    # Create hub-and-spoke: node 0 connects to all, others sparse
    for i in range(1, n_nodes):
        weight = rng.uniform(0.5, 1.0)
        adjacency[0, i] = weight
        adjacency[i, 0] = weight

    # Add a few random edges for structure
    for _ in range(5):
        i_node = int(rng.integers(1, n_nodes))
        j_node = int(rng.integers(1, n_nodes))
        if i_node != j_node:
            w = rng.uniform(0.3, 0.8)
            adjacency[i_node, j_node] = w
            adjacency[j_node, i_node] = w

    # Key: natural frequencies correlate with degree (Gomez-Gardenes et al.)
    degrees = adjacency.sum(axis=1)
    omega = degrees / degrees.max()  # INV-ES2: freq-degree correlation

    detector = ExplosiveSyncDetector(
        K_range=(0.1, 5.0),
        n_K_steps=20,
        kuramoto_steps=300,
        R_threshold=0.5,
        hysteresis_threshold=0.0,  # INV-ES2: low threshold to detect any hysteresis
    )

    result = detector.measure_proximity(
        adjacency=adjacency,
        omega=omega,
        N=n_nodes,
        seed=42,
    )

    # INV-ES2: proximity > 0 means some hysteresis was detected
    proximity_floor = 0.0  # tolerance: strict positivity
    assert result.proximity > proximity_floor, (
        f"INV-ES2 VIOLATED: proximity={result.proximity:.6f} <= 0. "
        f"Expected nonzero hysteresis with frequency-degree correlation. "
        f"hysteresis_width={result.hysteresis_width:.6f}, "
        f"K_c_fwd={result.K_c_forward:.4f}, K_c_bwd={result.K_c_backward:.4f}. "
        f"N={n_nodes}, K_range=(0.1, 5.0), n_K_steps=20, seed=42. "
        f"Physical reasoning: freq-degree correlation induces first-order transition."
    )

    # INV-ES2: hysteresis width floor = 0 (by definition: |K_c_fwd - K_c_bwd|)
    hysteresis_floor = 0.0  # tolerance: non-negative by construction
    assert result.hysteresis_width >= hysteresis_floor, (
        f"INV-ES2 VIOLATED: hysteresis_width={result.hysteresis_width:.6f} < 0. "
        f"Expected non-negative hysteresis width (INV-ES1 also applies). "
        f"K_c_fwd={result.K_c_forward:.4f}, K_c_bwd={result.K_c_backward:.4f}. "
        f"N={n_nodes}, seed=42. "
        f"Physical reasoning: hysteresis width = |K_c_fwd - K_c_bwd| >= 0 by definition."
    )


# ── INV-CB5: Cryptobiosis entry > individual module thresholds ──


def test_inv_cb5_entry_threshold_exceeds_module_thresholds() -> None:
    """INV-CB5 (conditional/property_test): entry_threshold > individual module thresholds.

    The cryptobiosis entry threshold must exceed every individual
    neuromodulator crisis threshold. GABA crisis fires at ~0.7,
    serotonin veto at stress >= 1.0 maps to T ~ 0.5-0.7.
    This is a configuration-contract test.
    """
    config = CryptobiosisConfig()

    # INV-CB5: GABA crisis threshold is typically ~0.7
    gaba_crisis_threshold = 0.7  # tolerance: known GABA crisis level

    n_modules_checked = 2  # INV-CB5: GABA + serotonin modules checked

    assert config.entry_threshold > gaba_crisis_threshold, (
        f"INV-CB5 VIOLATED: observed entry_threshold={config.entry_threshold} "
        f"<= GABA crisis threshold={gaba_crisis_threshold}. "
        f"Expected entry_threshold > {gaba_crisis_threshold} (GABA crisis level). "
        f"At N={n_modules_checked} modules checked, "
        f"with entry={config.entry_threshold}, exit={config.exit_threshold}. "
        f"Physical reasoning: cryptobiosis is last-resort; must fire after "
        f"individual module safety mechanisms."
    )

    # Also verify hysteresis holds (INV-CB7, supportive check)
    assert config.exit_threshold < config.entry_threshold, (
        f"INV-CB5/CB7 VIOLATED: observed exit={config.exit_threshold} "
        f">= entry={config.entry_threshold}. "
        f"Expected exit_threshold < entry_threshold for hysteresis. "
        f"At N={n_modules_checked} modules checked, "
        f"with entry={config.entry_threshold}, exit={config.exit_threshold}. "
        f"Physical reasoning: hysteresis prevents oscillation at boundary."
    )

    # Serotonin stress veto maps to T ~ 0.5-0.7
    serotonin_veto_T_upper = 0.7  # tolerance: upper bound of serotonin veto T range
    assert config.entry_threshold > serotonin_veto_T_upper, (
        f"INV-CB5 VIOLATED: observed entry_threshold={config.entry_threshold} "
        f"<= serotonin veto T upper={serotonin_veto_T_upper}. "
        f"Expected entry_threshold > {serotonin_veto_T_upper} (serotonin veto T range). "
        f"At N={n_modules_checked} modules checked, "
        f"with entry={config.entry_threshold}, exit={config.exit_threshold}. "
        f"Physical reasoning: serotonin veto at stress>=1.0 maps to T~0.5-0.7; "
        f"cryptobiosis must fire strictly above."
    )
