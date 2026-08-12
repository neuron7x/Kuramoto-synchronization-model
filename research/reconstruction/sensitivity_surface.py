# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002 — Gate 6 sensitivity surface / MDE map.

The X-10R E2E pipeline (PR #648) returned `NO_SIGNAL` on the
canonical 25-bank synthetic substrate. That output is honest but
*ambiguous* — it could mean "the precursor isn't there" OR "the
instrument is blind in this regime". A Minimum Detectable Effect
map (MDE) closes the ambiguity: for a given (N, structural-signal
strength) cell, what fraction of bootstrap-seed runs flips Gate 6
to PASS?

This module ships:

    SensitivityCell       — one (N, lambda, n_seeds) result row
    SensitivitySurface    — the full grid
    compute_sensitivity_surface(...) — driver
    mix_substrate_with_null(W, lambda_, rng) — controls true ΔR

The "lambda mixing" trick
=========================
We control the true precursor strength by linearly mixing the
reconstructed adjacency W_recon with a topology-randomised null
W_null:

    W_mixed(λ) = λ · W_recon + (1 − λ) · W_null

with W_null = shuffle_offdiag(W_recon). At λ=1 we have the full
structural signal; at λ=0 we have pure null (true ΔR ≡ 0). λ
between 0 and 1 produces a continuum of true precursor strengths.
This lets us measure:

  * **power(λ)** = P(Gate 6 PASSES | mixed at λ)
  * **FPR**      = power(λ=0) — false-positive rate at zero signal
  * **MDE**      = smallest λ where power ≥ 0.80 AND FPR ≤ 0.05

Strict scope contract
=====================
This module does NOT operate on real data. It does NOT emit any
bank-level claim or DoV verdict. Every cell is synthetic. Real
BIS Gate 6 verdicts remain forbidden by INV-IDENTIFICATION-1
until the substrate-discovery layer lands.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from research.reconstruction.kuramoto_on_reconstruction import (
    DEFAULT_BOOTSTRAP_SEEDS,
    DEFAULT_K_TEST_RATIO,
    MIN_PRECURSOR_GAP,
    PrecursorDirection,
    gate_6_precursor_discriminative,
)
from research.reconstruction.positive_control import ground_truth_core_periphery


@dataclass(frozen=True)
class SensitivityCell:
    """One (N, λ) result row.

    `lambda_mix` is the mixing weight: λ=1 ⇒ full structural signal;
    λ=0 ⇒ pure null (FPR-measuring cell).
    """

    n_nodes: int
    lambda_mix: float
    n_seeds: int
    n_pass: int
    n_facilitated: int
    n_hindered: int
    n_no_signal: int
    median_delta_r: float
    median_ci_width: float
    median_abs_delta_r: float

    @property
    def power(self) -> float:
        """Fraction of bootstrap-seed runs where Gate 6 PASSES."""
        return self.n_pass / self.n_seeds if self.n_seeds else 0.0

    @property
    def signed_direction_dominant(self) -> str:
        """Most-frequent precursor direction across seeds."""
        counts = {
            "facilitated": self.n_facilitated,
            "hindered": self.n_hindered,
            "no_signal": self.n_no_signal,
        }
        return max(counts, key=lambda k: counts[k])


@dataclass(frozen=True)
class SensitivitySurface:
    """Full sweep result + MDE finding."""

    n_grid: tuple[int, ...]
    lambda_grid: tuple[float, ...]
    n_seeds: int
    cells: tuple[SensitivityCell, ...]
    fpr_estimate: float
    """Power at λ=0 averaged across N (estimate of false-positive rate)."""
    mde_lambda_per_n: dict[int, float] = field(default_factory=dict)
    """Smallest λ where power ≥ 0.80 (per N). Inf if no cell clears."""

    def cell(self, *, n: int, lambda_mix: float) -> SensitivityCell | None:
        for c in self.cells:
            if c.n_nodes == n and abs(c.lambda_mix - lambda_mix) < 1e-9:
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        # Coerce inf → None so the output is valid strict-JSON.
        mde_safe: dict[int, float | None] = {
            n: (None if not (v < float("inf")) else float(v))
            for n, v in self.mde_lambda_per_n.items()
        }
        return {
            "n_grid": list(self.n_grid),
            "lambda_grid": list(self.lambda_grid),
            "n_seeds": self.n_seeds,
            "fpr_estimate": self.fpr_estimate,
            "mde_lambda_per_n": mde_safe,
            "cells": [
                {
                    "n_nodes": c.n_nodes,
                    "lambda_mix": c.lambda_mix,
                    "n_seeds": c.n_seeds,
                    "n_pass": c.n_pass,
                    "power": c.power,
                    "n_facilitated": c.n_facilitated,
                    "n_hindered": c.n_hindered,
                    "n_no_signal": c.n_no_signal,
                    "median_delta_r": c.median_delta_r,
                    "median_ci_width": c.median_ci_width,
                    "median_abs_delta_r": c.median_abs_delta_r,
                    "signed_direction_dominant": c.signed_direction_dominant,
                }
                for c in self.cells
            ],
        }


def mix_substrate_with_null(
    w: np.ndarray, *, lambda_mix: float, rng: np.random.Generator
) -> np.ndarray:
    """Mix the structural substrate with a topology-randomised null.

    `lambda_mix=1` returns w unchanged. `lambda_mix=0` returns the
    pure null. Intermediate values produce a controlled true
    precursor strength.

    The null is constructed by shuffling off-diagonal entries of w.
    """
    if not (0.0 <= lambda_mix <= 1.0):
        raise ValueError(f"lambda_mix must be in [0, 1]; got {lambda_mix}")
    if w.ndim != 2 or w.shape[0] != w.shape[1]:
        raise ValueError(f"w must be square 2-D; got {w.shape}")

    n = w.shape[0]
    flat = w.copy().reshape(-1)
    diag_idx = np.arange(n) * n + np.arange(n)
    mask = np.ones(n * n, dtype=bool)
    mask[diag_idx] = False
    off = flat[mask].copy()
    rng.shuffle(off)
    null_flat = flat.copy()
    null_flat[mask] = off
    w_null = null_flat.reshape(n, n).astype(np.float64)
    np.fill_diagonal(w_null, 0.0)
    mixed = lambda_mix * w + (1.0 - lambda_mix) * w_null
    np.fill_diagonal(mixed, 0.0)
    return mixed.astype(np.float64)


def compute_sensitivity_surface(
    *,
    n_grid: Sequence[int] = (50, 100, 200),
    lambda_grid: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.0),
    n_seeds: int = 20,
    substrate_seed: int = 42,
    k_ratio: float = DEFAULT_K_TEST_RATIO,
    n_bootstrap: int = DEFAULT_BOOTSTRAP_SEEDS,
    min_gap: float = MIN_PRECURSOR_GAP,
) -> SensitivitySurface:
    """Run the (N × λ × seeds) Gate 6 sweep and return the surface.

    For each cell:
      * Build a core-periphery substrate at N (deterministic seed).
      * For each of `n_seeds` bootstrap seeds, mix the substrate with
        the null at λ and call `gate_6_precursor_discriminative`.
      * Aggregate: n_pass, direction histogram, median ΔR, CI width.

    Reports:
      * `fpr_estimate` — average power across N at λ=0.
      * `mde_lambda_per_n` — smallest λ where power ≥ 0.80 per N
        (∞ when no cell clears).
    """
    cells: list[SensitivityCell] = []

    for n in n_grid:
        w_substrate = ground_truth_core_periphery(n=n, core_frac=0.30, seed=substrate_seed)
        for lam in lambda_grid:
            n_pass = 0
            n_fac = 0
            n_hind = 0
            n_nosig = 0
            delta_rs: list[float] = []
            ci_widths: list[float] = []
            for s in range(n_seeds):
                seed = substrate_seed * 1000 + n * 31 + int(lam * 1000) + s
                rng_mix = np.random.default_rng(seed)
                w_mixed = mix_substrate_with_null(w_substrate, lambda_mix=lam, rng=rng_mix)
                report = gate_6_precursor_discriminative(
                    w_mixed,
                    seed=seed + 7,
                    k_ratio=k_ratio,
                    n_bootstrap=n_bootstrap,
                    min_gap=min_gap,
                )
                if report.passed:
                    n_pass += 1
                if report.direction is PrecursorDirection.SYNCHRONIZATION_FACILITATED:
                    n_fac += 1
                elif report.direction is PrecursorDirection.SYNCHRONIZATION_HINDERED:
                    n_hind += 1
                else:
                    n_nosig += 1
                delta_rs.append(report.delta_r_median)
                ci_widths.append(report.delta_r_ci_high - report.delta_r_ci_low)
            cells.append(
                SensitivityCell(
                    n_nodes=int(n),
                    lambda_mix=float(lam),
                    n_seeds=int(n_seeds),
                    n_pass=int(n_pass),
                    n_facilitated=int(n_fac),
                    n_hindered=int(n_hind),
                    n_no_signal=int(n_nosig),
                    median_delta_r=float(np.median(delta_rs)),
                    median_ci_width=float(np.median(ci_widths)),
                    median_abs_delta_r=float(np.median(np.abs(delta_rs))),
                )
            )

    # FPR estimate = average power at λ=0.
    zero_cells = [c for c in cells if c.lambda_mix == 0.0]
    fpr = float(np.mean([c.power for c in zero_cells])) if zero_cells else 0.0

    # MDE per N: smallest λ where power ≥ 0.80.
    mde: dict[int, float] = {}
    for n in n_grid:
        cells_for_n = sorted((c for c in cells if c.n_nodes == n), key=lambda c: c.lambda_mix)
        found = False
        for c in cells_for_n:
            if c.power >= 0.80:
                mde[int(n)] = float(c.lambda_mix)
                found = True
                break
        if not found:
            mde[int(n)] = float("inf")

    return SensitivitySurface(
        n_grid=tuple(int(n) for n in n_grid),
        lambda_grid=tuple(float(x) for x in lambda_grid),
        n_seeds=int(n_seeds),
        cells=tuple(cells),
        fpr_estimate=fpr,
        mde_lambda_per_n=mde,
    )
