# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""BankLevelMarginalsCertificate — the allocator's evidence surface.

Per X-10R-1 (epic #638), the country-to-bank allocator emits a
certificate whose `cert_id` is bit-exact replay-stable for the same
(prior, country aggregates) pair. The certificate carries provenance
fields the X-10R reconstruction's domain-of-validity gate will later
consult: which prior was used, what fraction of banks the prior had
real evidence for, and what fallback policy filled the rest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class BankLevelMarginalsCertificate:
    """Frozen evidence record for one allocator run.

    Conservation contract (enforced by the allocator at construction):
      For every country c that appears in `bank_country_map`:
          Σ s_out[i] over banks i in country c == agg_out[c]      (to 1e-9 rel)
          Σ s_in[i]  over banks i in country c == agg_in[c]       (to 1e-9 rel)

    Replay contract:
      `cert_id` = sha256 over the full canonical payload (prior_id,
      bank_country_map, marginals rounded to 12 decimals, fallback
      policy, coverage ratio, totals). Same inputs ⇒ same cert_id;
      ANY input perturbation flips the hash.
    """

    prior_id: str
    n_countries: int
    n_banks: int
    coverage_ratio: float
    fallback_policy: str
    bank_country_map: tuple[tuple[str, str], ...]
    s_in: np.ndarray  # shape (n_banks,), float64
    s_out: np.ndarray  # shape (n_banks,), float64
    country_aggregates_in: tuple[tuple[str, float], ...]
    country_aggregates_out: tuple[tuple[str, float], ...]
    cert_id: str

    def __post_init__(self) -> None:
        if not (0.0 <= self.coverage_ratio <= 1.0):
            raise ValueError(f"coverage_ratio must be in [0, 1]; got {self.coverage_ratio}")
        if self.s_in.shape != (self.n_banks,) or self.s_out.shape != (self.n_banks,):
            raise ValueError(
                "s_in / s_out shapes must equal (n_banks,); "
                f"got s_in={self.s_in.shape}, s_out={self.s_out.shape}, "
                f"n_banks={self.n_banks}"
            )
        if self.s_in.dtype != np.float64 or self.s_out.dtype != np.float64:
            raise ValueError("s_in / s_out must be float64")
        if not self.cert_id or len(self.cert_id) != 64:
            raise ValueError(f"cert_id must be 64-char sha256 hex; got {self.cert_id!r}")
        try:
            int(self.cert_id, 16)
        except ValueError as e:
            raise ValueError(f"cert_id must be hexadecimal: {e}") from e
        if np.any(self.s_in < 0) or np.any(self.s_out < 0):
            raise ValueError("s_in / s_out must be non-negative")

    def serialise(self) -> dict[str, Any]:
        return {
            "prior_id": self.prior_id,
            "n_countries": self.n_countries,
            "n_banks": self.n_banks,
            "coverage_ratio": self.coverage_ratio,
            "fallback_policy": self.fallback_policy,
            "bank_country_map": [list(p) for p in self.bank_country_map],
            "s_in": [round(float(x), 12) for x in self.s_in],
            "s_out": [round(float(x), 12) for x in self.s_out],
            "country_aggregates_in": [list(p) for p in self.country_aggregates_in],
            "country_aggregates_out": [list(p) for p in self.country_aggregates_out],
            "cert_id": self.cert_id,
        }


def compute_cert_id(
    *,
    prior_id: str,
    bank_country_map: tuple[tuple[str, str], ...],
    s_in: np.ndarray,
    s_out: np.ndarray,
    country_aggregates_in: tuple[tuple[str, float], ...],
    country_aggregates_out: tuple[tuple[str, float], ...],
    coverage_ratio: float,
    fallback_policy: str,
) -> str:
    """Stable sha256 over the canonical allocator payload.

    Round to 12 decimals before hashing to match
    ``ReconstructionCapsule`` rounding (PR #635). This makes
    allocator and reconstruction cert IDs comparable in unit
    tolerance — both are stable to ULP-scale perturbations and
    insensitive to subnormal flush.
    """
    payload = (
        f"prior_id={prior_id}|"
        f"map={tuple(bank_country_map)}|"
        f"s_in={tuple(round(float(x), 12) for x in s_in)}|"
        f"s_out={tuple(round(float(x), 12) for x in s_out)}|"
        f"agg_in={tuple((c, round(v, 12)) for c, v in country_aggregates_in)}|"
        f"agg_out={tuple((c, round(v, 12)) for c, v in country_aggregates_out)}|"
        f"coverage={round(coverage_ratio, 12)}|"
        f"fallback={fallback_policy}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
