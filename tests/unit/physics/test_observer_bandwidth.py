# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for INV-OBSERVER-BANDWIDTH (P2, conditional, SPECULATIVE)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.physics.observer_bandwidth import (
    PROVENANCE_TIER,
    assess_bandwidth_bound,
    decoherence_rate_hz,
    observer_bandwidth_hz,
)


def test_provenance_tier_is_speculative() -> None:
    """Provenance tier must be SPECULATIVE — refs Zurek/Lieb-Robinson are adjacent, not derivative.

    Discrete tier; no float score. SPECULATIVE → P2 cap (validator check 5).
    """
    assert PROVENANCE_TIER == "SPECULATIVE"


def test_decoherence_rate_zero_is_isolated_system() -> None:
    """Γ = 0 means perfect isolation — accepted, no exception."""
    d = decoherence_rate_hz(0.0)
    assert d.rate_hz == 0.0


def test_observer_bandwidth_zero_is_passive_observer() -> None:
    """Σ̇ = 0 means the observer acquires no bits — accepted."""
    b = observer_bandwidth_hz(0.0)
    assert b.bits_per_second == 0.0


def test_decoherence_rate_negative_raises() -> None:
    """Negative rate is unphysical — fail-closed."""
    with pytest.raises(ValueError):
        decoherence_rate_hz(-1.0)


def test_observer_bandwidth_negative_raises() -> None:
    """Negative bandwidth is unphysical — fail-closed."""
    with pytest.raises(ValueError):
        observer_bandwidth_hz(-1.0)


def test_decoherence_rate_non_finite_raises() -> None:
    """INV-HPC2: NaN / Inf rate is fail-closed."""
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            decoherence_rate_hz(bad)


def test_observer_bandwidth_non_finite_raises() -> None:
    """INV-HPC2: NaN / Inf bandwidth is fail-closed."""
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            observer_bandwidth_hz(bad)


def test_bound_consistent_when_gamma_below_bandwidth() -> None:
    """Γ = 1 Hz, Σ̇ = 10 bit/s ⇒ slack = 9 Hz, consistent."""
    witness = assess_bandwidth_bound(decoherence_rate_hz(1.0), observer_bandwidth_hz(10.0))
    assert witness.is_bound_consistent is True
    assert witness.slack_hz == 9.0
    assert witness.reason is None


def test_bound_at_equality_is_consistent() -> None:
    """Γ = Σ̇ is the saturation case — boundary admissible."""
    witness = assess_bandwidth_bound(decoherence_rate_hz(5.0), observer_bandwidth_hz(5.0))
    assert witness.is_bound_consistent is True
    assert witness.slack_hz == 0.0


def test_bound_violated_when_gamma_above_bandwidth() -> None:
    """Γ = 10 Hz, Σ̇ = 1 bit/s ⇒ negative slack, INV violated."""
    witness = assess_bandwidth_bound(decoherence_rate_hz(10.0), observer_bandwidth_hz(1.0))
    assert witness.is_bound_consistent is False
    assert witness.slack_hz == -9.0
    assert witness.reason is not None
    assert "INV-OBSERVER-BANDWIDTH" in witness.reason


def test_passive_observer_blocks_any_positive_decoherence() -> None:
    """Σ̇ = 0 ⇒ any Γ > 0 is a violation (consistent with definition)."""
    witness = assess_bandwidth_bound(decoherence_rate_hz(1e-9), observer_bandwidth_hz(0.0))
    assert witness.is_bound_consistent is False


def test_witness_dataclass_is_frozen() -> None:
    """BandwidthWitness is immutable post-construction."""
    witness = assess_bandwidth_bound(decoherence_rate_hz(0.0), observer_bandwidth_hz(0.0))
    with pytest.raises(AttributeError):
        witness.is_bound_consistent = False  # type: ignore[misc]


@given(
    gamma=st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False),
    sigma=st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False),
)
def test_property_consistent_iff_gamma_le_sigma(gamma: float, sigma: float) -> None:
    """Property: bound is consistent iff Γ ≤ Σ̇."""
    witness = assess_bandwidth_bound(decoherence_rate_hz(gamma), observer_bandwidth_hz(sigma))
    expected = gamma <= sigma
    assert witness.is_bound_consistent is expected
