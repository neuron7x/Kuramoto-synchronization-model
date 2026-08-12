# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""SizeWeightedPrior — first concrete prior beyond the UniformPrior anchor.

Per X-10R-1 PR #2 (epic #638 follow-up to PR #1):

Real-world allocator priors land in two layers:

  1. A **registry** layer (which banks are resident in which country)
     — ECB MFI list, FDIC call reports, ICIJ Offshore Leaks reverse
     — every concrete prior must know this. UniformPrior already
     uses a registry internally.

  2. A **size signal** layer (relative size of each registered bank)
     — EBA transparency disclosures, Moody's BankFocus / Orbis,
     central bank supervisory disclosures. Without size signal a
     prior degenerates to 1/k and is identical to UniformPrior.

This module ships the size-signal layer in the simplest possible
form: a per-bank scalar weight, with shares proportional to weight
within country. The closed-form contract is

    expected_share(c, b) = weight[b] / Σ_{b' resident in c} weight[b']

Sources for real per-bank size signals (subsequent epic PRs):
  * `EBATransparencyPrior` — total assets from the latest EBA
    transparency exercise (annual; 119 banks / 25 EU+EEA; public).
  * `BankFocusPrior`       — Moody's BankFocus / Orbis Bank Focus
    extract (license-gated; richer coverage than EBA but commercial).

This PR ships the *constructor* with synthetic weights for tests.
A subsequent PR will load real EBA total-assets into the same
constructor.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SizeWeightedPrior:
    """Per-bank size-weighted prior over country-resident banks.

    Parameters
    ----------
    bank_country_map:
        Ordered tuple of ``(bank_id, country)`` — the registry
        layer. Same shape the allocator already consumes.
    bank_weights:
        Mapping ``{bank_id -> non-negative float}``. The *size
        signal*. Banks present in ``bank_country_map`` but missing
        from this mapping fall back to the per-country mean of
        the banks that DO have a weight; if no bank in the country
        has a weight, ``has_evidence(country)`` returns False so
        the allocator can apply its declared fallback policy.
    prior_id_tag:
        Stable identifier to attach to the certificate; default
        ``"size_weighted"``. A subsequent PR loading real EBA data
        will pass ``"eba_transparency_2024Q4"`` etc.
    """

    bank_country_map: tuple[tuple[str, str], ...]
    bank_weights: dict[str, float] = field(default_factory=dict)
    prior_id_tag: str = "size_weighted"

    def __post_init__(self) -> None:
        for bank_id, w in self.bank_weights.items():
            if not (w >= 0):  # also catches NaN
                raise ValueError(
                    f"bank_weights[{bank_id!r}] must be a non-negative finite number; got {w}"
                )
        # Detect a degenerate prior right at construction so a misuse
        # surfaces here, not at allocation time.
        countries = {c for _, c in self.bank_country_map}
        if not countries:
            raise ValueError("bank_country_map must be non-empty")

    @property
    def prior_id(self) -> str:
        return self.prior_id_tag

    def banks_in(self, country: str) -> tuple[str, ...]:
        return tuple(b for b, c in self.bank_country_map if c == country)

    def _country_weight_total(self, country: str) -> float:
        """Σ weights over banks resident in `country` AND with a weight.

        Used both by has_evidence (positive ⇒ True) and by the
        fallback computation in expected_share.
        """
        return float(
            sum(self.bank_weights[b] for b in self.banks_in(country) if b in self.bank_weights)
        )

    def has_evidence(self, country: str) -> bool:
        if not any(c == country for _, c in self.bank_country_map):
            return False
        # Evidence exists iff at least one resident bank has a weight
        # AND the country's total resident weight is positive.
        return self._country_weight_total(country) > 0.0

    def expected_share(self, *, country: str, bank_id: str) -> float:
        banks = self.banks_in(country)
        if not banks:
            raise ValueError(f"SizeWeightedPrior has no banks recorded for country {country!r}")
        if bank_id not in banks:
            raise ValueError(f"bank_id {bank_id!r} is not resident in country {country!r}")
        total_weight = self._country_weight_total(country)
        if total_weight <= 0:
            # No size signal at all — degenerate to 1/k. The allocator
            # may instead apply its fallback policy depending on
            # has_evidence — that path is exercised in the prior tests.
            return 1.0 / len(banks)
        # Per-bank weight, defaulting to per-country mean for banks
        # missing from `bank_weights`. Mean is the maximum-entropy
        # imputation for missing entries: it minimises the prior's
        # impact on the unobserved share without spuriously zeroing it.
        n_with_weight = sum(1 for b in banks if b in self.bank_weights)
        country_mean = total_weight / n_with_weight if n_with_weight else 0.0
        weight = self.bank_weights.get(bank_id, country_mean)
        # Effective denominator: sum of (weights ∪ imputed-mean-for-missing).
        n_missing = len(banks) - n_with_weight
        effective_total = total_weight + country_mean * n_missing
        if effective_total <= 0:
            return 1.0 / len(banks)
        return float(weight / effective_total)
