# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""InstrumentScope — declares the operational regime in which a score
function is allowed to emit a verdict. Out of regime → OUT_OF_SCOPE.

Closes B-line failure modes by forcing every score function to declare
its operational envelope BEFORE running on data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InstrumentScope:
    """Operational scope of a scoring instrument.

    ``instrument_id`` should be ``sha256(score_fn_source + semver)`` so that
    any silent change to the instrument invalidates downstream certificates.
    """

    instrument_id: str
    valid_for_substrate: str  # e.g. 'undirected_weighted_country_aggregate'
    valid_for_n_range: tuple[int, int]  # inclusive on both ends
    valid_for_density_range: tuple[float, float]
    valid_for_obs_per_corr: int  # min observations for any reported Pearson
    invalid_for: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        n_lo, n_hi = self.valid_for_n_range
        if not (isinstance(n_lo, int) and isinstance(n_hi, int)):
            raise TypeError("valid_for_n_range must be (int, int)")
        if n_lo < 0 or n_hi < n_lo:
            raise ValueError(f"invalid n_range: {self.valid_for_n_range}")
        d_lo, d_hi = self.valid_for_density_range
        if not (0.0 <= d_lo <= d_hi <= 1.0):
            raise ValueError(f"invalid density_range: {self.valid_for_density_range}")
        if self.valid_for_obs_per_corr < 2:
            raise ValueError("valid_for_obs_per_corr must be >= 2")
        # Required negative declarations — bank-level + tick data MUST be
        # in `invalid_for` for any country-aggregate scope.
        if self.valid_for_substrate.startswith("undirected_weighted_country"):
            for required in ("bank_level", "tick_data"):
                if required not in self.invalid_for:
                    raise ValueError(
                        f"country-aggregate scope must declare {required!r} as invalid"
                    )


def make_instrument_id(score_fn_source: str, semver: str) -> str:
    """sha256(source || '|' || semver) — canonical instrument identity."""
    payload = f"{score_fn_source}|{semver}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scope_match(
    scope: InstrumentScope,
    *,
    n: int,
    substrate: str,
    density: float,
    obs_per_corr: int | None = None,
) -> bool:
    """Return True iff the operational regime fits the declared scope.

    Iter-4 audit: rejects bool/float/non-int n and bool obs_per_corr that
    were previously coerced silently. Booleans subclass int in Python, so
    explicit type-check is required to keep ``scope_match(... n=True ...)``
    from being treated as ``n=1``.
    """
    if not isinstance(substrate, str) or isinstance(substrate, bool):
        return False
    if not isinstance(n, int) or isinstance(n, bool):
        return False
    if not isinstance(density, (int, float)) or isinstance(density, bool):
        return False
    if obs_per_corr is not None and (
        not isinstance(obs_per_corr, int) or isinstance(obs_per_corr, bool)
    ):
        return False
    if substrate != scope.valid_for_substrate:
        return False
    if substrate in scope.invalid_for:
        return False
    n_lo, n_hi = scope.valid_for_n_range
    if not (n_lo <= n <= n_hi):
        return False
    d_lo, d_hi = scope.valid_for_density_range
    if not (d_lo <= density <= d_hi):
        return False
    if obs_per_corr is not None and obs_per_corr < scope.valid_for_obs_per_corr:
        return False
    return True


def country_aggregate_default_scope(
    score_fn_source: str = "", semver: str = "0.0.0"
) -> InstrumentScope:
    """Default BIS LBS country-aggregate scope used by the Disha artefact."""
    return InstrumentScope(
        instrument_id=make_instrument_id(score_fn_source, semver),
        valid_for_substrate="undirected_weighted_country_aggregate",
        valid_for_n_range=(28, 35),
        valid_for_density_range=(0.05, 0.40),
        valid_for_obs_per_corr=8,
        invalid_for=("bank_level", "tick_data", "intraday", "tx_level"),
    )


def serialise_scope(scope: InstrumentScope) -> dict[str, Any]:
    """Stable JSON-friendly dict for capsule serialisation."""
    return {
        "instrument_id": scope.instrument_id,
        "valid_for_substrate": scope.valid_for_substrate,
        "valid_for_n_range": list(scope.valid_for_n_range),
        "valid_for_density_range": list(scope.valid_for_density_range),
        "valid_for_obs_per_corr": scope.valid_for_obs_per_corr,
        "invalid_for": list(scope.invalid_for),
    }
