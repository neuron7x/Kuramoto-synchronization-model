# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Registry loader — parses a per-country bank list into the
deterministic ordered ``bank_country_map`` shape the allocator and
priors consume.

Real-world registry sources land in subsequent epic PRs:

  * ECB MFI list (TSV/CSV at ``ecb.europa.eu/stats/financial_corporations
    /list_of_financial_institutions/html/``) — the canonical
    "monetary financial institution" registry for the euro area.
  * FDIC institutions list (CSV at ``fdic.gov``) — US-side equivalent.

This module ships the *parser surface* that those PRs will plug into.
It accepts already-parsed Python data (``dict[country, list[bank_id]]``)
and returns the canonical ``bank_country_map`` tuple. Disk-loading
PRs will call this helper after parsing their format-of-record.
"""

from __future__ import annotations


def registry_to_bank_country_map(
    registry: dict[str, list[str]],
) -> tuple[tuple[str, str], ...]:
    """Convert a ``{country: [bank_ids]}`` mapping to the canonical
    ``bank_country_map`` tuple consumed by ``AllocatorPrior``
    implementations and ``CountryToBankAllocator``.

    Parameters
    ----------
    registry:
        ``{country -> ordered list of resident bank identifiers}``.
        Bank identifiers must be unique GLOBALLY (not just within a
        country); otherwise the allocator's per-bank index would be
        ambiguous.

    Returns
    -------
    A deterministic tuple of ``(bank_id, country)`` pairs sorted
    primarily by country (alphabetical) and secondarily by the order
    each bank appears in its country list. Determinism is mandatory
    for the allocator's bit-exact replay contract (GATE_A4).
    """
    if not registry:
        raise ValueError("registry must be non-empty")

    seen_banks: set[str] = set()
    out: list[tuple[str, str]] = []
    for country in sorted(registry.keys()):
        if not country or not isinstance(country, str):
            raise ValueError(f"every country key must be a non-empty string; got {country!r}")
        banks = registry[country]
        if not banks:
            raise ValueError(
                f"country {country!r} has empty bank list; "
                "drop the country from the registry before passing it in"
            )
        for bank_id in banks:
            if not bank_id or not isinstance(bank_id, str):
                raise ValueError(
                    f"every bank_id must be a non-empty string; got {bank_id!r} in {country!r}"
                )
            if bank_id in seen_banks:
                raise ValueError(
                    f"bank_id {bank_id!r} appears in multiple countries; "
                    "bank identifiers must be globally unique"
                )
            seen_banks.add(bank_id)
            out.append((bank_id, country))
    return tuple(out)
