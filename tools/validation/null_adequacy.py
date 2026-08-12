# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Null-adequacy enforcement primitive (Task 03).

Where temporal/phase structure matters, an i.i.d. null (Gaussian, constant) is
inadequate (see ``audit_gaussian_null_sufficiency``): it clears any
structure-sensitive statistic trivially. This module is the fail-closed gate
that callers on a claim-bearing path use before trusting a null comparison:
``require_structure_preserving_null`` refuses an i.i.d. null when the series it
is meant to challenge is autocorrelated.

It is a guard, not a claim. It does not assert any signal exists; it only
refuses an inadmissible null choice.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

#: Nulls that preserve temporal/phase/graph structure — admissible where
#: structure matters. Names match the repo's generators.
STRUCTURE_PRESERVING: frozenset[str] = frozenset(
    {
        "phase_shuffle",
        "make_phase_shuffled_surrogate",
        "iaaft",
        "iaaft_surrogate",
        "block_bootstrap",
        "n3_block_bootstrap",
        "n4_iaaft",
        "degree_preserving",
        "n5_degree_preserving_graph",
    }
)

#: Nulls that destroy temporal structure — inadmissible for autocorrelated data.
IID_NULLS: frozenset[str] = frozenset(
    {"gaussian", "make_gaussian_null", "constant", "make_constant_null"}
)

#: Lag-1 autocorrelation above which a series counts as autocorrelated.
DEFAULT_AUTOCORR_THRESHOLD = 0.2


def lag1_autocorr(series: NDArray[np.float64]) -> float:
    x = np.asarray(series, dtype=np.float64).ravel()
    if x.size < 2:
        return 0.0
    x = x - x.mean()
    denom = float(np.sum(x * x))
    if denom == 0.0:
        return 0.0
    return float(np.sum(x[:-1] * x[1:]) / denom)


def is_structure_preserving(null_kind: str) -> bool:
    return null_kind.strip().lower() in STRUCTURE_PRESERVING


def require_structure_preserving_null(
    series: NDArray[np.float64],
    null_kind: str,
    *,
    threshold: float = DEFAULT_AUTOCORR_THRESHOLD,
) -> None:
    """Fail closed if *series* is autocorrelated but *null_kind* is i.i.d.

    Raises ``ValueError`` so a claim-bearing path cannot silently challenge an
    autocorrelated statistic with a structure-destroying null.
    """
    kind = null_kind.strip().lower()
    if is_structure_preserving(kind):
        return
    ac = abs(lag1_autocorr(series))
    if ac >= threshold and kind in IID_NULLS:
        raise ValueError(
            f"null '{null_kind}' is i.i.d. but the series is autocorrelated "
            f"(|lag-1 acf|={ac:.3f} >= {threshold}); use a structure-preserving null "
            f"(one of {sorted(STRUCTURE_PRESERVING)})"
        )
    if kind not in IID_NULLS:
        raise ValueError(
            f"unknown null kind {null_kind!r}; declare it structure-preserving or i.i.d."
        )
