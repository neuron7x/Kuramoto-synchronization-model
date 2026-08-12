# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Parameter jitter stability.

Given a frozen parameter vector and a user-provided evaluator that maps
candidate parameters → scalar out-of-sample Sharpe, this module perturbs
each parameter independently within a ±jitter band and reports:

- the Sharpe delta distribution,
- whether the *median perturbed* Sharpe stays within ``sharpe_tol`` of
  the anchor Sharpe,
- the fraction of candidates inside the tolerance band,
- min/max Sharpe across perturbations.

Pure-function API; evaluator is injected. No I/O. No writes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Evaluator = Callable[[Mapping[str, float]], float]


@dataclass(frozen=True)
class JitterStabilityResult:
    """Summary of a parameter-jitter stability run."""

    anchor_sharpe: float
    perturbed_sharpes: tuple[float, ...]
    sharpe_delta_median: float
    sharpe_delta_min: float
    sharpe_delta_max: float
    fraction_within_tol: float
    sharpe_tolerance: float
    n_candidates: int
    parameter_names: tuple[str, ...]


def parameter_jitter_stability(
    anchor_parameters: Mapping[str, float],
    evaluator: Evaluator,
    *,
    jitter_fractions: Mapping[str, float],
    n_candidates: int,
    sharpe_tolerance: float,
    seed: int = 42,
) -> JitterStabilityResult:
    """Evaluate stability of the anchor Sharpe under bounded jitter.

    Parameters
    ----------
    anchor_parameters
        Frozen parameters; each key is perturbed independently.
    evaluator
        Pure function mapping a candidate parameter dict → Sharpe. The
        evaluator must be *read-only* on any external state; jitter
        suites are required to pass a PLACEHOLDER marker when the
        evaluator cannot yet rebuild the full strategy.
    jitter_fractions
        For each parameter, the fraction of its anchor value used as the
        ±jitter band (e.g. ``{"cost_bps": 0.2}`` → ±20 %). Keys missing
        from this map are *not* perturbed.
    n_candidates
        Total number of jittered candidates to evaluate (anchor
        excluded).
    sharpe_tolerance
        Absolute Sharpe delta within which a candidate is "inside band".
    seed
        Seed for the perturbation RNG (deterministic).

    Raises
    ------
    ValueError
        If any jitter fraction is negative, if ``n_candidates < 1``,
        or if a parameter in ``jitter_fractions`` is missing from
        ``anchor_parameters``.
    """
    if n_candidates < 1:
        raise ValueError(f"n_candidates must be >= 1, got {n_candidates}")
    for name, frac in jitter_fractions.items():
        if name not in anchor_parameters:
            raise ValueError(f"jitter_fractions references unknown parameter {name!r}")
        if frac < 0:
            raise ValueError(f"jitter_fractions[{name!r}] must be >= 0, got {frac}")

    anchor_sharpe = float(evaluator(dict(anchor_parameters)))
    rng = np.random.default_rng(seed)
    names = tuple(jitter_fractions.keys())

    perturbed: NDArray[np.float64] = np.empty(n_candidates, dtype=np.float64)
    for i in range(n_candidates):
        candidate: dict[str, float] = {k: float(v) for k, v in anchor_parameters.items()}
        for name in names:
            frac = jitter_fractions[name]
            anchor_value = float(anchor_parameters[name])
            delta = rng.uniform(-frac, frac) * anchor_value
            candidate[name] = anchor_value + delta
        perturbed[i] = float(evaluator(candidate))

    deltas = perturbed - anchor_sharpe
    within = np.sum(np.abs(deltas) <= sharpe_tolerance)
    return JitterStabilityResult(
        anchor_sharpe=anchor_sharpe,
        perturbed_sharpes=tuple(float(x) for x in perturbed),
        sharpe_delta_median=float(np.median(deltas)),
        sharpe_delta_min=float(deltas.min()),
        sharpe_delta_max=float(deltas.max()),
        fraction_within_tol=float(within / n_candidates),
        sharpe_tolerance=sharpe_tolerance,
        n_candidates=n_candidates,
        parameter_names=names,
    )
