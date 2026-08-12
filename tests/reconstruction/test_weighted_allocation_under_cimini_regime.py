# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-001 — `allocate_weights` under the OPERATIONAL Cimini regime.

The original `test_weighted_allocation.py` exercises
`allocate_weights` against UNIFORM-Bernoulli supports
(``p = 0.30``). That regime is convenient for unit-testing IPF
convergence but does NOT match production: real X-10R runs
generate ``p_ij`` from `fit_cimini_squartini` — heterogeneous,
heavy-tailed, dominated by top-fitness pairs.

This module pins the operational-regime contract:

    For every density d in {0.03, 0.05, 0.08, 0.12}:
      1. Synthesize lognormal s_out, s_in (mass-balanced).
      2. fit_cimini_squartini(s_out, s_in, target_density=d).
      3. p = p_link(fit.x, fit.y, fit.z).
      4. a = sample_adjacency_bernoulli(p, rng=...).
      5. w = allocate_weights(a, s_out, s_in).
      6. Measure row_L1 / col_L1 (Gate 5 metric class).
      7. Cell PASSES iff row_L1 ≤ 0.05 AND col_L1 ≤ 0.05.

Acceptance: ≥ 3 of 4 density cells pass.

Why ``≥ 3 of 4`` and not 4/4
=============================
At very low density (0.03) the Cimini support concentrates on
top-fitness pairs and IPF can leave structural residual on
heavy-tailed marginals. This is `documented` debt — Gate 5
catches the residual at the verdict boundary; the allocator does
NOT itself fail-closed. The 3/4 floor encodes that contract:
the operational regime must ALMOST always pass IPF; one density
cell may clip the threshold without the regime being
unfit-for-purpose.

A 4/4 floor would over-constrain — the regime test would
fail on a single unlucky seed at d=0.03 even when downstream
Gate 5 still catches the issue. A 3/4 floor matches the actual
production gate (Gate 5 is the verdict; this test is a
*regression* on the helper).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from research.reconstruction.cimini_squartini import (
    fit_cimini_squartini,
    p_link,
)
from research.reconstruction.weighted_allocation import (
    allocate_weights,
    sample_adjacency_bernoulli,
)

_DENSITIES: tuple[float, ...] = (0.03, 0.05, 0.08, 0.12)
_GATE5_L1_THRESHOLD: float = 0.05
_REQUIRED_PASS_COUNT: int = 3  # ≥ 3 of 4 cells

_REPORT_PATH = Path("tmp/x10r_weighted_allocation_operational_regime.json")


def _operational_marginals(n: int, *, sigma: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Heavy-tailed lognormal marginals, mass-balanced (Σs_in=Σs_out)."""
    rng = np.random.default_rng(seed)
    s_out = rng.lognormal(mean=10.0, sigma=sigma, size=n)
    s_in = rng.lognormal(mean=10.0, sigma=sigma, size=n)
    s_in = s_in * (s_out.sum() / s_in.sum())
    return s_out, s_in


def _row_col_l1(w: np.ndarray, s_out: np.ndarray, s_in: np.ndarray) -> tuple[float, float]:
    """Return (row_L1, col_L1) per Gate 5 normalisation: relative to
    mean strength so the threshold (0.05) is dimension-free."""
    n = w.shape[0]
    s_out_recon = w.sum(axis=1)
    s_in_recon = w.sum(axis=0)
    mean_strength = float((s_out + s_in).mean() / 2.0)
    if mean_strength == 0:
        mean_strength = 1.0
    row = float(np.abs(s_out - s_out_recon).sum() / n / mean_strength)
    col = float(np.abs(s_in - s_in_recon).sum() / n / mean_strength)
    return row, col


def _run_cell(*, density: float, n: int, sigma: float, seed: int) -> dict[str, float | bool]:
    """One density cell: fit → sample → allocate → measure L1."""
    s_out, s_in = _operational_marginals(n, sigma=sigma, seed=seed)
    fit = fit_cimini_squartini(s_out, s_in, target_density=density)
    p = p_link(fit.x, fit.y, fit.z)
    rng = np.random.default_rng(seed * 31 + int(density * 1000))
    a = sample_adjacency_bernoulli(p, rng=rng)
    w = allocate_weights(a, s_out, s_in)
    row_l1, col_l1 = _row_col_l1(w, s_out, s_in)
    passed = (row_l1 <= _GATE5_L1_THRESHOLD) and (col_l1 <= _GATE5_L1_THRESHOLD)
    return {
        "density": float(density),
        "n_nodes": int(n),
        "sigma": float(sigma),
        "seed": int(seed),
        "row_l1": row_l1,
        "col_l1": col_l1,
        "passed": bool(passed),
    }


# ---------------------------------------------------------------------------
# Per-cell smoke tests — each density at the canonical seed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("density", _DENSITIES)
def test_cell_runs_without_crashing_at_canonical_seed(density: float) -> None:
    """Every density cell must complete without a crash at the
    canonical seed. The fit / sample / allocate stack must be
    operational-regime-stable."""
    cell = _run_cell(density=density, n=80, sigma=1.0, seed=42)
    assert "passed" in cell
    assert 0.0 <= cell["row_l1"] < 1.0
    assert 0.0 <= cell["col_l1"] < 1.0


# ---------------------------------------------------------------------------
# The operational-regime gate: ≥ 3 of 4 densities must clear Gate 5
# ---------------------------------------------------------------------------


def test_operational_regime_passes_three_of_four_densities() -> None:
    """The contract: under Cimini-calibrated p_ij + Bernoulli + IPF
    on lognormal marginals, ≥ 3 of 4 default-sweep densities must
    clear the Gate 5 row/col L1 ≤ 0.05 threshold.

    Producing a JSON report at tmp/x10r_weighted_allocation_
    operational_regime.json so the report markdown can be regenerated
    deterministically.
    """
    cells = [_run_cell(density=d, n=80, sigma=1.0, seed=42) for d in _DENSITIES]
    n_pass = sum(1 for c in cells if c["passed"])

    # Persist evidence (best-effort; tmp/ is gitignored).
    try:
        _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REPORT_PATH.write_text(json.dumps({"densities": cells, "n_pass": n_pass}, indent=2))
    except OSError:
        pass

    assert n_pass >= _REQUIRED_PASS_COUNT, (
        f"operational-regime gate failed: only {n_pass}/{len(_DENSITIES)} "
        f"densities cleared Gate 5 row/col L1 ≤ {_GATE5_L1_THRESHOLD}. "
        f"Cells: {cells}"
    )


# ---------------------------------------------------------------------------
# Multi-seed robustness — the regime should not be cherry-picked at seed=42
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_operational_regime_robust_across_seeds() -> None:
    """Across 3 seeds, the operational-regime gate must pass every
    time (each seed gets its own ≥ 3/4 outcome). Catches a regime
    that only works at the canonical seed."""
    seeds = (42, 17, 101)
    seed_outcomes: list[int] = []
    for s in seeds:
        cells = [_run_cell(density=d, n=80, sigma=1.0, seed=s) for d in _DENSITIES]
        seed_outcomes.append(sum(1 for c in cells if c["passed"]))
    assert all(n >= _REQUIRED_PASS_COUNT for n in seed_outcomes), (
        f"operational regime brittle across seeds: per-seed pass counts = "
        f"{dict(zip(seeds, seed_outcomes))}"
    )


# ---------------------------------------------------------------------------
# Heavy-tail stress — sigma=2.0 marginals (BIS-LBS-like)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_operational_regime_heavy_tail_sigma_2() -> None:
    """At sigma=2.0 the lognormal marginals approximate the heavier
    tails seen in BIS LBS country aggregates. The regime must still
    clear ≥ 2 of 4 densities (relaxed bar — heavy-tail IS the regime
    where IPF residual is hardest)."""
    cells = [_run_cell(density=d, n=80, sigma=2.0, seed=42) for d in _DENSITIES]
    n_pass = sum(1 for c in cells if c["passed"])
    assert (
        n_pass >= 2
    ), f"heavy-tail (sigma=2) regime broke: {n_pass}/4 densities cleared. Cells: {cells}"


# ---------------------------------------------------------------------------
# Conservation of mass remains exact regardless of IPF residual
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("density", _DENSITIES)
def test_total_mass_conserved_in_cimini_regime(density: float) -> None:
    """Even when row/col L1 clip the threshold, the TOTAL mass
    must be conserved to FLOATING-POINT tolerance: Σ w_ij ≡ Σ s_out
    (= Σ s_in). This is GATE_2 at the global level — a tight bound,
    NOT a gross sanity check.

    Per Codex P2 review on PR #649: a 1 % envelope hides a real
    0.5 % leakage regression. The bound below (10 × N × ipf_tol)
    matches the actual IPF contract: the global sum's deviation is
    upper-bounded by `N × per_row_tol`, where per_row_tol is the
    ipf_tol times the maximum marginal. We harden to 10× that
    bound to leave a small safety margin for floating-point
    round-off in the comparator while still rejecting any
    meaningful (≥ 1e-7 relative) conservation regression.
    """
    n = 80
    s_out, s_in = _operational_marginals(n, sigma=1.0, seed=42)
    fit = fit_cimini_squartini(s_out, s_in, target_density=density)
    p = p_link(fit.x, fit.y, fit.z)
    rng = np.random.default_rng(7919 + int(density * 1000))
    a = sample_adjacency_bernoulli(p, rng=rng)
    w = allocate_weights(a, s_out, s_in)
    total_w = float(w.sum())
    total_s = float(s_out.sum())
    # Hard bound: relative drift < 1e-7. Every density should
    # satisfy this exactly because the IPF projection enforces
    # column marginals to ipf_tol = 1e-9 relative to max(s), and
    # the global sum is just the col marginals' sum.
    rel_drift = abs(total_w - total_s) / total_s
    assert (
        rel_drift < 1e-7
    ), f"total mass not conserved at density={density}: Σw={total_w:.4f} vs Σs={total_s:.4f}"
