#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Structurally INDEPENDENT reference confidence sequence for a Bernoulli mean
(CRCC task T2 / P1 theorem-to-code parity).

Production (scripts/ci/prospective_reviewer_value.py) uses a Beta-Binomial
MIXTURE e-value inverted by Ville. This reference uses a DIFFERENT mechanism: a
normal-mixture sub-Gaussian time-uniform boundary (Robbins method of mixtures;
Howard, Ramdas, McAuliffe, Sekhon 2021, "Time-uniform, nonparametric,
nonasymptotic confidence sequences"). Two different constructions covering the
same estimand is the parity control — agreement is evidence the *property*, not
one implementation, holds.

Theorem used (normal mixture, two-sided):
  For increments X_i - p bounded in [0,1] (1/4-sub-Gaussian), with intrinsic
  variance process V_t = t/4 and tuning rho>0, the boundary
      B_t = sqrt( 2 (V_t + rho) * log( sqrt(V_t/rho + 1) / alpha ) )
  satisfies  P( exists t : |S_t - t p| > B_t ) <= alpha,   S_t = sum_{i<=t} X_i.
  Hence  CS_t = [ X̄_t - B_t/t , X̄_t + B_t/t ]  has time-uniform coverage >= 1-alpha.

Assumptions -> executable preconditions:
  A1 X_i in [0,1]            -> inputs are 0/1 (asserted by the caller's Bernoulli draw)
  A2 sub-Gaussian sigma^2=1/4 -> hard-coded VAR = 0.25 (Hoeffding for [0,1])
  A3 alpha in (0,1)          -> checked
  A4 rho > 0                 -> checked
This module makes NO stopping decision and holds NO authority.
"""

from __future__ import annotations

import math

VAR = 0.25  # 1/4-sub-Gaussian parameter for a [0,1] variable (Hoeffding)


def boundary(t: int, alpha: float, rho: float) -> float:
    """Normal-mixture uniform boundary on |S_t - t p| at level alpha."""
    if t <= 0:
        return math.inf
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha in (0,1)")
    if rho <= 0.0:
        raise ValueError("rho > 0")
    v = t * VAR
    return math.sqrt(2.0 * (v + rho) * math.log(math.sqrt(v / rho + 1.0) / alpha))


def in_cs(successes: int, n: int, p: float, alpha: float = 0.05, rho: float = 1.0) -> bool:
    """Is p inside the reference CS at time n? |S_n - n p| <= B_n."""
    if n <= 0:
        return True
    return abs(successes - n * p) <= boundary(n, alpha, rho)


def interval(successes: int, n: int, alpha: float = 0.05, rho: float = 1.0) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    r = boundary(n, alpha, rho) / n
    m = successes / n
    return max(0.0, m - r), min(1.0, m + r)


if __name__ == "__main__":
    # sanity: boundary shrinks per-mean radius as n grows; p=0 and p=1 handled.
    for n in (1, 10, 100, 1000):
        print(f"n={n:5} radius={boundary(n,0.05,1.0)/n:.4f}  p=0 in CS(0/n): {in_cs(0,n,0.0)}")
