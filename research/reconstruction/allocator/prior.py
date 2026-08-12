# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""AllocatorPrior — dependency-injection seam for country-to-bank allocation.

Per the X-10R-1 allocator epic (GH issue #638), bank-level inference
from BIS country-aggregate marginals is a TWO-STEP inverse problem:

    (country aggregates) ── allocator ──▶ (bank-level marginals)
                                                      │
                                                      ▼
                                          X-10R Cimini-Squartini
                                          reconstruction (PR #635 + #641)

The allocator splits a country's bilateral aggregate among the banks
resident there. *How* it splits is the prior's job. This module
defines the protocol every prior must satisfy and ships a
``UniformPrior`` baseline that places equal share on every resident
bank — the degenerate prior that all subsequent priors are measured
against (if a real-world prior cannot beat the uniform prior on
synthetic ground-truth recovery, the prior is doing no work).

Subsequent epic PRs add concrete priors:
  * `ECBMFIPrior`           — ECB Monetary Financial Institutions list
  * `EBATransparencyPrior`  — EBA transparency exercise (119 banks /
                              25 EU+EEA countries)
  * `BankFocusPrior`        — Moody's BankFocus / Orbis Bank Focus
                              (license-gated)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class AllocatorPrior(Protocol):
    """A prior over how a country's bilateral aggregate is split
    among the banks resident there.

    Every prior MUST satisfy:

      * ``banks_in(country)`` returns a deterministic, ordered tuple
        of bank identifiers (used downstream for stable hashing of
        allocator certificates — non-deterministic order ⇒ the
        certificate's bit-exact replay contract breaks).

      * ``expected_share(country, bank_id)`` returns a non-negative
        float; ``Σ expected_share(c, b) for b in banks_in(c) ≈ 1``
        (the allocator renormalises to enforce exact conservation,
        but the prior must give a normalisable distribution).

      * ``has_evidence(country)`` returns True iff the prior has
        actual data for the country — False ⇒ the prior is falling
        back to a default (e.g. uniform). Surfaced in the allocator
        certificate's ``coverage_ratio`` for provenance.

      * ``prior_id`` is a stable string identifier carried into the
        certificate so reviewers can trace which prior produced
        which bank-level marginals.
    """

    @property
    def prior_id(self) -> str:
        """Stable identifier (e.g., "uniform", "ecb_mfi_2024_q4")."""
        ...

    def banks_in(self, country: str) -> tuple[str, ...]:
        """Ordered tuple of resident bank identifiers."""
        ...

    def expected_share(self, *, country: str, bank_id: str) -> float:
        """Non-negative share of the country aggregate attributable
        to ``bank_id``. Must sum to ≈ 1 across ``banks_in(country)``.
        """
        ...

    def has_evidence(self, country: str) -> bool:
        """True iff the prior carries actual data for this country
        (vs falling back to a default)."""
        ...


@dataclass(frozen=True)
class UniformPrior:
    """Equal-share baseline: every resident bank gets 1/k of the
    country aggregate, where k = number of resident banks.

    This is the *falsification anchor* for the allocator epic. If a
    candidate prior cannot beat the uniform prior on synthetic
    ground-truth recovery (Gate-5-style metrics on bank-level
    marginals), the prior is uninformative and shipping it would be
    method theatre. Subsequent priors are required to surface
    "improvement over UniformPrior" as part of their PR evidence.

    The prior takes a frozen mapping ``{country -> tuple[bank_id, ...]}``
    so banks_in is deterministic. The mapping is passed in at
    construction (rather than discovered dynamically) so the
    certificate's bit-exact replay contract is hermetic.
    """

    bank_country_map: tuple[tuple[str, str], ...]
    """Ordered (bank_id, country) pairs — the source of truth for
    banks_in / has_evidence."""

    @property
    def prior_id(self) -> str:
        return "uniform"

    def banks_in(self, country: str) -> tuple[str, ...]:
        return tuple(b for b, c in self.bank_country_map if c == country)

    def expected_share(self, *, country: str, bank_id: str) -> float:
        banks = self.banks_in(country)
        if not banks:
            raise ValueError(f"UniformPrior has no banks recorded for country {country!r}")
        if bank_id not in banks:
            raise ValueError(f"bank_id {bank_id!r} is not resident in country {country!r}")
        return 1.0 / len(banks)

    def has_evidence(self, country: str) -> bool:
        # UniformPrior carries no real-world evidence — every country
        # it knows about is a "uniform-fallback" by definition.
        # `True` means "I have an opinion to offer" — the opinion just
        # happens to be 1/k. Falsification anchor: this is what a
        # prior with NO information looks like.
        return any(c == country for _, c in self.bank_country_map)
