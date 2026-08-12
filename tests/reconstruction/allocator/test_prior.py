# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the AllocatorPrior protocol + UniformPrior implementation."""

from __future__ import annotations

import pytest

from research.reconstruction.allocator.prior import (
    AllocatorPrior,
    UniformPrior,
)


def _bcm() -> tuple[tuple[str, str], ...]:
    return (
        ("BankA1", "C1"),
        ("BankA2", "C1"),
        ("BankA3", "C1"),
        ("BankB1", "C2"),
        ("BankB2", "C2"),
    )


def test_uniform_prior_satisfies_protocol() -> None:
    p = UniformPrior(bank_country_map=_bcm())
    # Runtime protocol check.
    assert isinstance(p, AllocatorPrior)


def test_uniform_prior_id_is_stable() -> None:
    assert UniformPrior(bank_country_map=_bcm()).prior_id == "uniform"


def test_uniform_banks_in_returns_correct_subset() -> None:
    p = UniformPrior(bank_country_map=_bcm())
    assert p.banks_in("C1") == ("BankA1", "BankA2", "BankA3")
    assert p.banks_in("C2") == ("BankB1", "BankB2")
    assert p.banks_in("UNKNOWN") == ()


def test_uniform_expected_share_is_inverse_count() -> None:
    p = UniformPrior(bank_country_map=_bcm())
    assert p.expected_share(country="C1", bank_id="BankA1") == pytest.approx(1.0 / 3)
    assert p.expected_share(country="C1", bank_id="BankA2") == pytest.approx(1.0 / 3)
    assert p.expected_share(country="C2", bank_id="BankB1") == 0.5


def test_uniform_expected_share_sums_to_one() -> None:
    p = UniformPrior(bank_country_map=_bcm())
    for country in ("C1", "C2"):
        total = sum(p.expected_share(country=country, bank_id=b) for b in p.banks_in(country))
        assert total == pytest.approx(1.0, abs=1e-12)


def test_uniform_expected_share_rejects_unknown_country() -> None:
    p = UniformPrior(bank_country_map=_bcm())
    with pytest.raises(ValueError, match="no banks"):
        p.expected_share(country="UNKNOWN", bank_id="BankA1")


def test_uniform_expected_share_rejects_non_resident_bank() -> None:
    p = UniformPrior(bank_country_map=_bcm())
    with pytest.raises(ValueError, match="not resident"):
        p.expected_share(country="C1", bank_id="BankB1")


def test_uniform_has_evidence_only_for_known_countries() -> None:
    p = UniformPrior(bank_country_map=_bcm())
    assert p.has_evidence("C1") is True
    assert p.has_evidence("C2") is True
    assert p.has_evidence("UNKNOWN") is False


def test_uniform_prior_is_hashable_for_use_in_keys() -> None:
    """Frozen dataclass ⇒ hashable. Allocator may key caches by prior."""
    p = UniformPrior(bank_country_map=_bcm())
    {p}
