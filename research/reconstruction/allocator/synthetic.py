# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic country aggregates with KNOWN bank-level ground truth.

Per X-10R-1 (epic #638), the allocator's positive-control surface
needs synthetic substrates where we know what the right answer is —
otherwise we cannot certify that any prior is doing useful work.

The construction is straightforward:

  1. Pick `n_countries` × `n_banks_per_country`.
  2. For each country, sample bank shares from a chosen distribution
     (`uniform`, `lognormal`, `pareto`).
  3. Renormalise shares to 1.
  4. Sample a country-aggregate scale from another distribution.
  5. Bank-level marginals = share × country-aggregate-scale.
  6. Country aggregates = Σ bank-level marginals over residents
     (round-trip equality is exact by construction).

Returned: `(country_aggregates_in, country_aggregates_out,
ground_truth_s_in, ground_truth_s_out, bank_country_map)`. The
allocator under test is run against the country aggregates; its
emitted bank-level marginals are then compared to the ground truth
via Gate-5-style metrics (relative L1 per country, top-k Jaccard,
etc.).
"""

from __future__ import annotations

from typing import Literal

import numpy as np

ShareDistribution = Literal["uniform", "lognormal", "pareto"]


def _sample_shares(
    *, n: int, distribution: ShareDistribution, rng: np.random.Generator
) -> np.ndarray:
    """Sample `n` non-negative shares from the chosen distribution.

    Caller is responsible for renormalisation.
    """
    if n <= 0:
        raise ValueError(f"n must be positive; got {n}")
    if distribution == "uniform":
        raw: np.ndarray = rng.uniform(0.5, 1.5, size=n).astype(np.float64)
    elif distribution == "lognormal":
        raw = rng.lognormal(mean=0.0, sigma=1.0, size=n).astype(np.float64)
    elif distribution == "pareto":
        # Pareto with shape α=2 — heavy-tailed, top bank dominates.
        raw = (rng.pareto(a=2.0, size=n) + 1.0).astype(np.float64)
    else:
        raise ValueError(
            f"unknown distribution {distribution!r}; "
            "must be one of 'uniform', 'lognormal', 'pareto'"
        )
    return raw


def synthetic_country_aggregates(
    *,
    n_countries: int = 5,
    n_banks_per_country: int = 8,
    share_distribution: ShareDistribution = "lognormal",
    aggregate_scale_mean: float = 12.0,
    aggregate_scale_sigma: float = 1.0,
    seed: int = 42,
) -> tuple[
    dict[str, float],
    dict[str, float],
    np.ndarray,
    np.ndarray,
    tuple[tuple[str, str], ...],
]:
    """Generate country aggregates with KNOWN bank-level ground truth.

    Returns
    -------
    country_aggregates_in:
        Mapping country → in-aggregate. Built as Σ ground_truth_s_in
        over residents — round-trip equality is exact by construction.
    country_aggregates_out:
        Same for out-aggregate.
    ground_truth_s_in:
        ``np.ndarray`` shape (n_countries × n_banks_per_country,)
        — the bank-level in-strengths the allocator should recover.
    ground_truth_s_out:
        Same shape, bank-level out-strengths.
    bank_country_map:
        Ordered tuple of ``(bank_id, country)`` pairs the allocator
        consumes; deterministic across runs at fixed seed.
    """
    if n_countries <= 0:
        raise ValueError(f"n_countries must be positive; got {n_countries}")
    if n_banks_per_country <= 0:
        raise ValueError(f"n_banks_per_country must be positive; got {n_banks_per_country}")

    rng = np.random.default_rng(seed)
    n_banks_total = n_countries * n_banks_per_country

    bank_country_map: list[tuple[str, str]] = []
    for c_idx in range(n_countries):
        country = f"C{c_idx:02d}"
        for b_idx in range(n_banks_per_country):
            bank_country_map.append((f"B{c_idx:02d}_{b_idx:02d}", country))
    bank_country_map_t = tuple(bank_country_map)

    s_in = np.zeros(n_banks_total, dtype=np.float64)
    s_out = np.zeros(n_banks_total, dtype=np.float64)
    country_aggregates_in: dict[str, float] = {}
    country_aggregates_out: dict[str, float] = {}

    for c_idx in range(n_countries):
        country = f"C{c_idx:02d}"
        agg_in_country = float(
            rng.lognormal(mean=aggregate_scale_mean, sigma=aggregate_scale_sigma)
        )
        agg_out_country = float(
            rng.lognormal(mean=aggregate_scale_mean, sigma=aggregate_scale_sigma)
        )

        shares_in = _sample_shares(n=n_banks_per_country, distribution=share_distribution, rng=rng)
        shares_in /= shares_in.sum()
        shares_out = _sample_shares(n=n_banks_per_country, distribution=share_distribution, rng=rng)
        shares_out /= shares_out.sum()

        offset = c_idx * n_banks_per_country
        s_in[offset : offset + n_banks_per_country] = shares_in * agg_in_country
        s_out[offset : offset + n_banks_per_country] = shares_out * agg_out_country

        # Country aggregate is the EXACT sum (no rounding loss).
        country_aggregates_in[country] = float(s_in[offset : offset + n_banks_per_country].sum())
        country_aggregates_out[country] = float(s_out[offset : offset + n_banks_per_country].sum())

    return (
        country_aggregates_in,
        country_aggregates_out,
        s_in,
        s_out,
        bank_country_map_t,
    )


def bank_level_recovery_l1(*, ground_truth: np.ndarray, allocated: np.ndarray) -> float:
    """Relative L1 error between recovered and ground-truth marginals.

    Returns ``Σ |gt - alloc| / Σ |gt|`` (clamped to a finite ratio).
    A pure ground-truth allocator returns 0; UniformPrior on a
    lognormal-share substrate returns a non-trivial positive number.
    """
    gt = np.asarray(ground_truth, dtype=np.float64).ravel()
    al = np.asarray(allocated, dtype=np.float64).ravel()
    if gt.shape != al.shape:
        raise ValueError(f"shape mismatch: gt={gt.shape}, alloc={al.shape}")
    denom = float(np.abs(gt).sum())
    if denom <= 0:
        return 0.0
    return float(np.abs(gt - al).sum() / denom)
