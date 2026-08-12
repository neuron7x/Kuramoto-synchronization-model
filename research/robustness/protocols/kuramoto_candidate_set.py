# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Anti-inflation guard for Kuramoto jitter candidates.

The strategy family is frozen by ``PARAMETER_LOCK.json``. The only
parameters that may enter a jitter sweep are those whose perturbation
preserves the research-line identity. Anything prefixed ``seed_``,
``random_`` or ``jitter_`` is rejected up front because such keys
smuggle nuisance axes into the candidate set and artificially deflate
PBO / inflate PSR by multiple testing on hidden DoF.

The guard lives at protocol level, not inside
:func:`research.robustness.stability.parameter_jitter_stability`, so
primitives stay strategy-agnostic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

FORBIDDEN_PREFIXES: Final[tuple[str, ...]] = ("seed_", "random_", "jitter_")


class CandidateSetInflationError(ValueError):
    """Raised when an inflated/forbidden parameter name is proposed."""


def validate_candidate_parameter_names(
    jitter_fractions: Mapping[str, float],
) -> None:
    """Reject candidate sets containing forbidden parameter name prefixes.

    Raises :class:`CandidateSetInflationError` listing every offender.
    """
    offenders = [
        name for name in jitter_fractions if any(name.startswith(p) for p in FORBIDDEN_PREFIXES)
    ]
    if offenders:
        raise CandidateSetInflationError(
            "forbidden candidate names (inflate PBO/PSR by hidden DoF): "
            + ", ".join(sorted(offenders))
        )


def assert_anchor_covers_candidates(
    anchor_parameters: Mapping[str, float],
    jitter_fractions: Mapping[str, float],
) -> None:
    """Every jittered name must exist in the anchor parameter vector."""
    missing = sorted(set(jitter_fractions) - set(anchor_parameters))
    if missing:
        raise CandidateSetInflationError(f"jitter parameters missing from anchor: {missing}")
