# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared data model for D-002J-P6 null-model hierarchy v1.

A *null model* in this hierarchy is NOT decorative rigor. Every null is a
FALSIFIER that targets exactly ONE named false explanation. A result that
"survives" a null only counts as information if the null genuinely could
have killed it.

Each null exposes ``apply(signal_array, seed, params) -> NullInstance``.
The :class:`NullInstance` carries the seed, the resolved params, the
nulled array, and two machine-checked dictionaries:

* ``preserved_invariants_checked`` — what the null CLAIMS to preserve,
  each mapped to the boolean result of an in-code numeric check.
* ``destroyed_structure_checked`` — what the null CLAIMS to destroy, each
  mapped to the boolean result of an in-code numeric check.

A null whose preserve/destroy claims are merely declared but not
numerically verified is rejected by the P6 guard tests. Determinism is a
hard contract: same ``(signal_array, seed, params)`` => bit-identical
``nulled_array``. No real data, no wall-clock, numpy only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

SCHEMA_NULL_INSTANCE: Final[str] = "D002J-NULL-INSTANCE-v1"
"""Schema version stamped onto every :class:`NullInstance`."""


@dataclass(frozen=True)
class NullInstance:
    """Frozen record of one deterministic null transformation.

    Attributes
    ----------
    null_id:
        Canonical null id (matches the null-hierarchy manifest
        ``null_id``, e.g. ``"N5_degree_preserving_graph_null"``).
    seed:
        Integer seed fed to ``numpy.random.default_rng``; same seed +
        same params + same input => bit-identical ``nulled_array``.
    params:
        The resolved parameter mapping actually used.
    nulled_array:
        The transformed array under the null hypothesis. For graph
        nulls this is the rewired adjacency matrix; for time-series
        nulls it is the surrogate series.
    preserved_invariants_checked:
        Mapping ``invariant_name -> bool``. ``True`` means the null was
        numerically verified to preserve that structure. ANY ``False``
        means the null failed its own admission test (fail-closed).
    destroyed_structure_checked:
        Mapping ``structure_name -> bool``. ``True`` means the null was
        numerically verified to destroy that structure. ANY ``False``
        means the null is a no-op for that structure and must be
        rejected (fail-closed).
    metadata:
        Free-form provenance: target false explanation, applicability,
        h_i2_conditional flag, schema version.
    """

    null_id: str
    seed: int
    params: dict[str, float]
    nulled_array: NDArray[Any]
    preserved_invariants_checked: dict[str, bool]
    destroyed_structure_checked: dict[str, bool]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # bounds: anti-decorative construction guard, not a physics
        # clamp. A NullInstance that cannot name what it preserves or
        # destroys is decorative rigor and must fail closed at creation.
        if not self.null_id:
            raise ValueError("NullInstance.null_id must be non-empty")
        if not self.preserved_invariants_checked:
            raise ValueError(
                f"NullInstance({self.null_id!r}).preserved_invariants_checked "
                "must declare and numerically check at least one preserved invariant"
            )
        if not self.destroyed_structure_checked:
            raise ValueError(
                f"NullInstance({self.null_id!r}).destroyed_structure_checked "
                "must declare and numerically check at least one destroyed structure"
            )

    @property
    def admitted(self) -> bool:
        """``True`` iff every preserve AND destroy check passed.

        This is the in-code admission test: a null is only admissible
        if it provably preserved everything it claims to preserve and
        provably destroyed everything it claims to destroy.
        """
        return all(self.preserved_invariants_checked.values()) and all(
            self.destroyed_structure_checked.values()
        )


def autocorr_at_lag(series: NDArray[np.float64], lag: int) -> float:
    """Return the lag-``lag`` sample autocorrelation of ``series``.

    Deterministic helper used by block-bootstrap admission checks.
    """
    if lag <= 0:
        raise ValueError(f"lag must be a positive int; got {lag}")
    x = np.asarray(series, dtype=np.float64)
    n = x.shape[0]
    if n <= lag:
        raise ValueError(f"series length {n} must exceed lag {lag}")
    xc = x - x.mean()
    denom = float(np.dot(xc, xc))
    if denom == 0.0:
        # bounds: a constant series has undefined autocorrelation; fail
        # closed rather than emit a silently-repaired 0.0.
        raise ValueError("autocorr undefined for a constant series (zero variance)")
    num = float(np.dot(xc[:-lag], xc[lag:]))
    return num / denom


def degree_sequence(adjacency: NDArray[np.float64]) -> NDArray[np.int64]:
    """Return the (binary) degree sequence of a square adjacency matrix."""
    a = np.asarray(adjacency, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError(f"adjacency must be square 2D; got shape {a.shape}")
    binary = (a != 0.0).astype(np.int64)
    out: NDArray[np.int64] = binary.sum(axis=1).astype(np.int64)
    return out
