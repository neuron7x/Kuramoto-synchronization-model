# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for registry → bank_country_map conversion."""

from __future__ import annotations

import pytest

from research.reconstruction.allocator.registry import registry_to_bank_country_map


def test_registry_to_map_returns_canonical_tuple_shape() -> None:
    bcm = registry_to_bank_country_map({"DE": ["DE-001", "DE-002"], "FR": ["FR-001"]})
    assert isinstance(bcm, tuple)
    for entry in bcm:
        assert isinstance(entry, tuple)
        assert len(entry) == 2


def test_registry_sorts_countries_alphabetically() -> None:
    """Country order in the canonical map must be deterministic
    (alphabetical) so the allocator's bit-exact replay contract is
    not seed-of-dict-order-dependent."""
    bcm = registry_to_bank_country_map({"FR": ["FR-001"], "DE": ["DE-001"], "AT": ["AT-001"]})
    countries = [c for _, c in bcm]
    assert countries == ["AT", "DE", "FR"]


def test_registry_preserves_within_country_bank_order() -> None:
    """Inside a country the order is the order the caller supplied —
    the registry parser should not re-sort within country."""
    bcm = registry_to_bank_country_map({"DE": ["DE-Z", "DE-A", "DE-M"]})
    banks = [b for b, _ in bcm]
    assert banks == ["DE-Z", "DE-A", "DE-M"]


def test_registry_rejects_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        registry_to_bank_country_map({})


def test_registry_rejects_country_with_empty_bank_list() -> None:
    with pytest.raises(ValueError, match="empty bank list"):
        registry_to_bank_country_map({"DE": []})


def test_registry_rejects_blank_country_key() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        registry_to_bank_country_map({"": ["BANK"]})


def test_registry_rejects_blank_bank_id() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        registry_to_bank_country_map({"DE": [""]})


def test_registry_rejects_duplicate_bank_across_countries() -> None:
    """Bank IDs must be globally unique. Two countries claiming the
    same bank ⇒ the allocator's per-bank index would be ambiguous."""
    with pytest.raises(ValueError, match="multiple countries"):
        registry_to_bank_country_map({"DE": ["DUP"], "FR": ["DUP"]})


def test_registry_round_trip_through_size_weighted_prior() -> None:
    """The map produced here must be a drop-in for the allocator."""
    from research.reconstruction.allocator import SizeWeightedPrior

    bcm = registry_to_bank_country_map({"DE": ["DE-001", "DE-002"], "FR": ["FR-001"]})
    p = SizeWeightedPrior(
        bank_country_map=bcm,
        bank_weights={"DE-001": 60.0, "DE-002": 40.0, "FR-001": 100.0},
    )
    assert p.banks_in("DE") == ("DE-001", "DE-002")
    assert p.expected_share(country="DE", bank_id="DE-001") == pytest.approx(0.6)


def test_registry_is_deterministic_for_same_input() -> None:
    """Two calls with the same registry dict must return the same map."""
    reg = {"DE": ["DE-001"], "FR": ["FR-001", "FR-002"]}
    a = registry_to_bank_country_map(reg)
    b = registry_to_bank_country_map(reg)
    assert a == b
