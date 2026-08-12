# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CountryToBankAllocator — split country aggregates into bank-level marginals.

Per X-10R-1 (epic #638), this is the deterministic split step in
the two-stage inverse problem:

    (country aggregates) ── allocator ──▶ (bank-level marginals)

The allocator is *prior-driven* — it consumes an `AllocatorPrior`
that defines the per-bank shares, then enforces exact conservation
per country (Σ shares ≡ 1 within each country) by renormalisation.

Conservation invariants (Allocator GATE_A1):
    Σ_b s_in[b in country]  ≡ country_aggregates_in[country]   to 1e-9 rel
    Σ_b s_out[b in country] ≡ country_aggregates_out[country]  to 1e-9 rel

Coverage invariant (Allocator GATE_A2):
    coverage_ratio = #{countries with prior evidence} / #countries.
    A reportable threshold; below the threshold the *consumer*
    (e.g. the X-10R reconstruction capsule) decides whether to
    accept the certificate. The allocator itself does NOT fail-
    closed here — it surfaces coverage as evidence. Conflating
    coverage with admissibility would couple two separate concerns.

Non-negativity invariant (Allocator GATE_A3):
    Every share in [0, 1]; every emitted marginal ≥ 0.

Replay invariant (Allocator GATE_A4):
    Same prior + same aggregates ⇒ same cert_id.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from research.reconstruction.allocator.certificate import (
    BankLevelMarginalsCertificate,
    compute_cert_id,
)
from research.reconstruction.allocator.prior import AllocatorPrior

_FALLBACK_POLICIES: frozenset[str] = frozenset({"uniform_within_country", "drop_country", "raise"})


@dataclass(frozen=True)
class CountryToBankAllocator:
    """Deterministic country-aggregate ➝ bank-marginal splitter.

    Parameters
    ----------
    prior:
        Any object implementing the ``AllocatorPrior`` protocol.
        Determines per-bank shares within each country.
    fallback_policy:
        How to handle countries the prior has no evidence for.
        ``"uniform_within_country"`` (default) — fall back to equal
        share among any banks the prior knows of in that country;
        ``"drop_country"`` — drop the country from the output and
        zero its aggregate;
        ``"raise"`` — raise ``ValueError`` (strictest mode).
    conservation_tolerance:
        Per-country relative-L1 tolerance on the sum-equality
        contract; default 1e-9.
    """

    prior: AllocatorPrior
    fallback_policy: str = "uniform_within_country"
    conservation_tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if self.fallback_policy not in _FALLBACK_POLICIES:
            raise ValueError(
                f"fallback_policy must be one of {sorted(_FALLBACK_POLICIES)}; "
                f"got {self.fallback_policy!r}"
            )
        if self.conservation_tolerance <= 0:
            raise ValueError(
                f"conservation_tolerance must be > 0; got {self.conservation_tolerance}"
            )

    def allocate(
        self,
        country_aggregates_in: dict[str, float],
        country_aggregates_out: dict[str, float],
        *,
        bank_country_map: tuple[tuple[str, str], ...],
    ) -> BankLevelMarginalsCertificate:
        """Split country aggregates into bank-level marginals.

        ``bank_country_map`` is the deterministic ordering used for
        the output arrays — the i-th entry of ``s_in`` / ``s_out``
        corresponds to ``bank_country_map[i][0]``.
        """
        if set(country_aggregates_in.keys()) != set(country_aggregates_out.keys()):
            raise ValueError(
                "country_aggregates_in and country_aggregates_out must "
                "cover the same set of countries"
            )
        if not bank_country_map:
            raise ValueError("bank_country_map must be non-empty")

        countries = sorted(country_aggregates_in.keys())
        # Sanity: every country in the aggregates must appear in the
        # bank map (otherwise we have aggregate mass with nowhere to go).
        bank_countries = {c for _, c in bank_country_map}
        missing = [c for c in countries if c not in bank_countries]
        if missing:
            if self.fallback_policy == "raise":
                raise ValueError(f"countries with no banks in bank_country_map: {missing}")
            # `drop_country` removes them; `uniform_within_country`
            # cannot place mass without banks, so it also drops.
            countries = [c for c in countries if c in bank_countries]

        n_banks = len(bank_country_map)
        bank_to_idx = {b: i for i, (b, _) in enumerate(bank_country_map)}
        s_in = np.zeros(n_banks, dtype=np.float64)
        s_out = np.zeros(n_banks, dtype=np.float64)

        countries_with_evidence = 0
        for country in countries:
            agg_in = float(country_aggregates_in[country])
            agg_out = float(country_aggregates_out[country])
            if agg_in < 0 or agg_out < 0:
                raise ValueError(
                    f"country aggregates must be non-negative; "
                    f"got in={agg_in}, out={agg_out} for {country!r}"
                )

            country_banks = self.prior.banks_in(country)
            if self.prior.has_evidence(country):
                countries_with_evidence += 1
                shares = np.array(
                    [self.prior.expected_share(country=country, bank_id=b) for b in country_banks],
                    dtype=np.float64,
                )
                if np.any(shares < 0):
                    raise ValueError(
                        f"prior {self.prior.prior_id!r} returned negative share "
                        f"for country {country!r}"
                    )
                total = float(shares.sum())
                if total <= 0:
                    if self.fallback_policy == "raise":
                        raise ValueError(
                            f"prior {self.prior.prior_id!r} produced zero total "
                            f"share for country {country!r}"
                        )
                    # Fallback: uniform.
                    shares = np.full(len(country_banks), 1.0 / len(country_banks))
                else:
                    shares = shares / total  # exact renormalisation
            else:
                if self.fallback_policy == "raise":
                    raise ValueError(
                        f"prior {self.prior.prior_id!r} has no evidence for "
                        f"country {country!r} and fallback_policy='raise'"
                    )
                if self.fallback_policy == "drop_country":
                    continue
                # uniform_within_country
                if not country_banks:
                    continue
                shares = np.full(len(country_banks), 1.0 / len(country_banks))

            for share, bank_id in zip(shares, country_banks, strict=True):
                idx = bank_to_idx[bank_id]
                s_in[idx] += share * agg_in
                s_out[idx] += share * agg_out

        # Verify conservation per country (Allocator GATE_A1).
        for country in countries:
            agg_in = float(country_aggregates_in[country])
            agg_out = float(country_aggregates_out[country])
            in_sum = sum(s_in[bank_to_idx[b]] for b, c in bank_country_map if c == country)
            out_sum = sum(s_out[bank_to_idx[b]] for b, c in bank_country_map if c == country)
            ref_in = max(agg_in, 1.0)
            ref_out = max(agg_out, 1.0)
            if abs(in_sum - agg_in) / ref_in > self.conservation_tolerance:
                raise ValueError(
                    f"GATE_A1 violated on {country!r}: Σ s_in = {in_sum:.6f}, agg_in = {agg_in:.6f}"
                )
            if abs(out_sum - agg_out) / ref_out > self.conservation_tolerance:
                raise ValueError(
                    f"GATE_A1 violated on {country!r}: "
                    f"Σ s_out = {out_sum:.6f}, agg_out = {agg_out:.6f}"
                )

        coverage_ratio = countries_with_evidence / len(countries) if countries else 0.0

        agg_in_tup = tuple(sorted(country_aggregates_in.items()))
        agg_out_tup = tuple(sorted(country_aggregates_out.items()))
        cert_id = compute_cert_id(
            prior_id=self.prior.prior_id,
            bank_country_map=bank_country_map,
            s_in=s_in,
            s_out=s_out,
            country_aggregates_in=agg_in_tup,
            country_aggregates_out=agg_out_tup,
            coverage_ratio=coverage_ratio,
            fallback_policy=self.fallback_policy,
        )

        return BankLevelMarginalsCertificate(
            prior_id=self.prior.prior_id,
            n_countries=len(countries),
            n_banks=n_banks,
            coverage_ratio=coverage_ratio,
            fallback_policy=self.fallback_policy,
            bank_country_map=bank_country_map,
            s_in=s_in,
            s_out=s_out,
            country_aggregates_in=agg_in_tup,
            country_aggregates_out=agg_out_tup,
            cert_id=cert_id,
        )
