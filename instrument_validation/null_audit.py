# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""NullAudit — full-distribution record of a candidate vs a null family.

Mean-only constructor is forbidden. The previous Disha artefact reported
``null_mean`` and a hardcoded ``min_required_margin = 0.05`` — unit-blind
and information-destroying. NullAudit forces every consumer to keep the
seven canonical quantiles and the empirical p-value.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

REQUIRED_QUANTILES: tuple[str, ...] = (
    "p2.5",
    "p10",
    "p25",
    "p50",
    "p75",
    "p90",
    "p97.5",
)

_MIN_NULL_DRAWS: int = 200


@dataclass(frozen=True)
class NullAudit:
    null_family: str
    null_mean: float
    null_std: float
    quantiles: dict[str, float]
    candidate: float
    candidate_percentile: float
    empirical_p_one_sided: float
    z_score: float
    n_null_draws: int
    null_draws_sha256: str
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.n_null_draws < _MIN_NULL_DRAWS:
            raise ValueError(f"n_null_draws={self.n_null_draws} < required {_MIN_NULL_DRAWS}")
        missing = [q for q in REQUIRED_QUANTILES if q not in self.quantiles]
        if missing:
            raise ValueError(
                f"NullAudit missing required quantiles: {missing}; mean-only constructor forbidden"
            )
        if not (0.0 <= self.candidate_percentile <= 100.0):
            raise ValueError(f"candidate_percentile out of range: {self.candidate_percentile}")
        if not (0.0 <= self.empirical_p_one_sided <= 1.0):
            raise ValueError(f"empirical_p_one_sided out of range: {self.empirical_p_one_sided}")
        if len(self.null_draws_sha256) != 64:
            raise ValueError("null_draws_sha256 must be 64-char sha256 hexdigest")


def _sha256_array(arr: np.ndarray) -> str:
    """Stable sha256 of a 1-D float array (sorted, 12-decimal rounded)."""
    if arr.size == 0:
        return hashlib.sha256(b"").hexdigest()
    rounded = np.round(np.sort(arr.astype(np.float64)), 12)
    return hashlib.sha256(rounded.tobytes()).hexdigest()


_VALID_ONE_SIDED: frozenset[str] = frozenset({"candidate_below_null", "candidate_above_null"})


def build_null_audit(
    *,
    null_family: str,
    null_draws: np.ndarray,
    candidate: float,
    one_sided: str = "candidate_below_null",
    extra: dict[str, Any] | None = None,
) -> NullAudit:
    """Construct a NullAudit from raw null draws + candidate value.

    ``one_sided`` ∈ {'candidate_below_null', 'candidate_above_null'}.
    """
    # Iter-4 audit: validate one_sided BEFORE doing 200-element percentile
    # work, so a typo fails fast rather than after expensive computation.
    if one_sided not in _VALID_ONE_SIDED:
        raise ValueError(f"one_sided must be one of {sorted(_VALID_ONE_SIDED)}; got {one_sided!r}")
    if not null_family:
        raise ValueError("null_family must be a non-empty string")
    arr = np.asarray(null_draws, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size < _MIN_NULL_DRAWS:
        raise ValueError(f"need >= {_MIN_NULL_DRAWS} finite null draws; got {arr.size}")
    qs = {
        "p2.5": float(np.percentile(arr, 2.5)),
        "p10": float(np.percentile(arr, 10.0)),
        "p25": float(np.percentile(arr, 25.0)),
        "p50": float(np.percentile(arr, 50.0)),
        "p75": float(np.percentile(arr, 75.0)),
        "p90": float(np.percentile(arr, 90.0)),
        "p97.5": float(np.percentile(arr, 97.5)),
    }
    cand = float(candidate)
    null_mean = float(arr.mean())
    null_std = float(arr.std(ddof=0))
    pct = float(100.0 * (arr < cand).sum() / arr.size)
    if one_sided == "candidate_below_null":
        p = float((arr <= cand).sum() / arr.size)
    elif one_sided == "candidate_above_null":
        p = float((arr >= cand).sum() / arr.size)
    else:
        raise ValueError(f"unknown one_sided: {one_sided!r}")
    z = float((cand - null_mean) / null_std) if null_std > 0 else float("nan")
    return NullAudit(
        null_family=null_family,
        null_mean=null_mean,
        null_std=null_std,
        quantiles=qs,
        candidate=cand,
        candidate_percentile=pct,
        empirical_p_one_sided=p,
        z_score=z,
        n_null_draws=int(arr.size),
        null_draws_sha256=_sha256_array(arr),
        extra=dict(extra or {}),
    )


def serialise_null_audit(audit: NullAudit) -> dict[str, Any]:
    return {
        "null_family": audit.null_family,
        "null_mean": audit.null_mean,
        "null_std": audit.null_std,
        "quantiles": dict(audit.quantiles),
        "candidate": audit.candidate,
        "candidate_percentile": audit.candidate_percentile,
        "empirical_p_one_sided": audit.empirical_p_one_sided,
        "z_score": audit.z_score,
        "n_null_draws": audit.n_null_draws,
        "null_draws_sha256": audit.null_draws_sha256,
        "extra": dict(audit.extra),
    }
