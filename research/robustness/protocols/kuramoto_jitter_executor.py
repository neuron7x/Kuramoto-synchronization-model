# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto jitter executor — interface-stable placeholder.

Rebuilding the strategy Sharpe under perturbed parameters requires the
raw asset panel (not in the frozen bundle). Until the jitter rebuild
path is wired, the executor returns an *analytic approximation*: a
smooth quadratic penalty in parameter-space distance scaled by the
anchor Sharpe. The approximation is deterministic and monotone, so the
jitter suite still exercises the primitive contract, but the Sharpe
deltas it produces must be interpreted as *interface-layer only*.

The runtime mode is exposed as :data:`EVALUATOR_MODE` and recorded
verbatim in the emitted robustness artifacts so a downstream reader can
never confuse placeholder evidence for live evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

EVALUATOR_MODE: Final[str] = "PLACEHOLDER_APPROXIMATION"

PlaceholderEvaluator = Callable[[Mapping[str, float]], float]


def make_placeholder_evaluator(
    anchor_sharpe: float,
    anchor_parameters: Mapping[str, float],
    curvature: float = 0.05,
) -> PlaceholderEvaluator:
    """Return a deterministic quadratic evaluator around the anchor.

    The returned callable maps a candidate parameter dict to a Sharpe
    that equals ``anchor_sharpe`` at the anchor and decays quadratically
    with the squared L2 distance in *fractional* parameter space (so
    parameters on different scales are comparable).

    Parameters
    ----------
    anchor_sharpe
        Sharpe at the anchor point.
    anchor_parameters
        Reference vector for fractional distance computation.
    curvature
        Quadratic-decay coefficient. Larger values penalise drift more.
    """
    anchor = {k: float(v) for k, v in anchor_parameters.items()}

    def _evaluate(candidate: Mapping[str, float]) -> float:
        sq = 0.0
        for name, value in candidate.items():
            if name not in anchor:
                continue
            ref = anchor[name]
            if ref == 0.0:
                continue
            d = (float(value) - ref) / ref
            sq += d * d
        return float(anchor_sharpe - curvature * sq)

    return _evaluate
