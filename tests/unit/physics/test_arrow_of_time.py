# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for INV-ARROW-OF-TIME (P0, monotonic).

Anchor: Landauer 1961 + Bennett 1982 (Maxwell demon resolution).
Provenance level: ANCHORED.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.physics.arrow_of_time import (
    PROVENANCE_TIER,
    ObserverEntropyLedger,
    assess_arrow_of_time,
    cumulative_arrow_of_time,
    landauer_floor_cost_bits,
    net_entropy_production_bits,
)


def _ledger(
    system_entropy_change_bits: float = 0.0,
    observer_information_gain_bits: float = 0.0,
) -> ObserverEntropyLedger:
    return ObserverEntropyLedger(
        system_entropy_change_bits=system_entropy_change_bits,
        observer_information_gain_bits=observer_information_gain_bits,
    )


def test_provenance_tier_is_anchored() -> None:
    """Provenance tier must be ANCHORED — Landauer + Bennett are peer-reviewed.

    Discrete tier; no float "truth-coherence" score (that introduced fake
    precision and was removed in chore/honest-provenance-cleanup).
    """
    assert PROVENANCE_TIER == "ANCHORED"


def test_landauer_floor_zero_information_gain_is_zero() -> None:
    """No information gained ⇒ no floor cost (degenerate case)."""
    assert landauer_floor_cost_bits(0.0) == 0.0


def test_landauer_floor_positive_information_gain_is_proportional() -> None:
    """Floor is bit-for-bit the information gain in bit-space proxy."""
    for bits in (0.5, 1.0, 7.0, 1e6):
        assert landauer_floor_cost_bits(bits) == bits


def test_landauer_floor_negative_information_gain_raises() -> None:
    """Negative gain is fail-closed — model erasure as a separate entry."""
    with pytest.raises(ValueError):
        landauer_floor_cost_bits(-1.0)


def test_landauer_floor_non_finite_raises() -> None:
    """INV-HPC2: NaN / Inf are fail-closed."""
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            landauer_floor_cost_bits(bad)


def test_net_entropy_zero_zero_is_zero() -> None:
    """No system change, no observation ⇒ zero net production."""
    ledger = _ledger()
    assert net_entropy_production_bits(ledger) == 0.0


def test_net_entropy_pure_system_increase_is_consistent() -> None:
    """Standard 2nd law: positive ΔS_system, no observer ⇒ Σ_net >= 0."""
    ledger = _ledger(system_entropy_change_bits=2.5)
    witness = assess_arrow_of_time(ledger)
    assert witness.is_arrow_consistent is True
    assert witness.net_entropy_production_bits == 2.5
    assert witness.reason is None


def test_maxwell_demon_balanced_is_consistent() -> None:
    """Apparent local reduction ΔS = -1 bit paid for by observer +1 bit info gain.

    Bennett 1982: Maxwell demon does not violate 2nd law because the
    information stored about the gas molecule's velocity costs at
    least k_B T ln 2 to erase (or hold). Σ_net == 0 here is the
    boundary case; equality permitted.
    """
    ledger = _ledger(system_entropy_change_bits=-1.0, observer_information_gain_bits=1.0)
    witness = assess_arrow_of_time(ledger)
    assert witness.is_arrow_consistent is True
    assert witness.net_entropy_production_bits == 0.0


def test_maxwell_demon_underpaid_is_inconsistent() -> None:
    """Apparent reduction ΔS = -2 bits not fully paid by 1 bit info gain ⇒ violation."""
    ledger = _ledger(system_entropy_change_bits=-2.0, observer_information_gain_bits=1.0)
    witness = assess_arrow_of_time(ledger)
    assert witness.is_arrow_consistent is False
    assert witness.net_entropy_production_bits == -1.0
    assert witness.reason is not None
    assert "INV-ARROW-OF-TIME" in witness.reason


def test_witness_is_frozen_dataclass() -> None:
    """ArrowOfTimeWitness is immutable post-construction."""
    witness = assess_arrow_of_time(_ledger())
    with pytest.raises(AttributeError):
        witness.is_arrow_consistent = False  # type: ignore[misc]


def test_cumulative_empty_window_raises() -> None:
    """No entries ⇒ no claim about the arrow; fail-closed not silent zero."""
    with pytest.raises(ValueError):
        cumulative_arrow_of_time([])


def test_cumulative_single_consistent_entry() -> None:
    """Single positive-Σ entry ⇒ cumulative equals that entry."""
    total = cumulative_arrow_of_time([_ledger(system_entropy_change_bits=3.0)])
    assert total == 3.0


def test_cumulative_local_violation_balanced_by_global_excess() -> None:
    """Window of three: -2, 0.5+1, +5 ⇒ each individually may violate, sum is still
    the relevant bookkeeping for the contiguous window. Cumulative >= 0 here."""
    entries = [
        _ledger(system_entropy_change_bits=-2.0, observer_information_gain_bits=1.5),
        _ledger(system_entropy_change_bits=5.0, observer_information_gain_bits=0.0),
    ]
    total = cumulative_arrow_of_time(entries)
    assert math.isclose(total, 4.5, rel_tol=1e-12)
    assert total >= 0.0


def test_cumulative_unpaid_window_is_negative_signal() -> None:
    """If the entire window has more local reductions than observer payments,
    cumulative_arrow_of_time returns a negative number — the caller is then
    obligated to fail-closed on this invariant."""
    entries = [
        _ledger(system_entropy_change_bits=-3.0, observer_information_gain_bits=1.0),
        _ledger(system_entropy_change_bits=-1.0, observer_information_gain_bits=0.5),
    ]
    total = cumulative_arrow_of_time(entries)
    assert total < 0.0


@given(
    delta_S=st.floats(
        min_value=-1e6,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
    delta_I=st.floats(
        min_value=0.0,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_arrow_consistent_iff_landauer_pays_for_local_reduction(
    delta_S: float, delta_I: float
) -> None:
    """Property: witness reports consistent iff ΔS + ΔI >= 0 (in bits)."""
    ledger = _ledger(system_entropy_change_bits=delta_S, observer_information_gain_bits=delta_I)
    witness = assess_arrow_of_time(ledger)
    expected_consistent = (delta_S + delta_I) >= 0.0
    assert witness.is_arrow_consistent is expected_consistent
