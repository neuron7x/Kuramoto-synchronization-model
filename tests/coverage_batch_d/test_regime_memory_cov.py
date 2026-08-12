# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coverage tests for geosync.neuroeconomics.regime_memory."""

from __future__ import annotations

import math

from geosync.neuroeconomics.regime_memory import RegimeMemory, TransitionInfo


def test_first_observation_returns_none_previous() -> None:
    mem = RegimeMemory()
    info = mem.observe("BTC", "COHERENT")
    assert isinstance(info, TransitionInfo)
    assert info.previous == "NONE"
    assert info.current == "COHERENT"
    assert info.probability == 1.0
    assert info.surprise == 0.0
    assert info.pattern is None


def test_previous_regime_not_in_index_returns_none_branch() -> None:
    mem = RegimeMemory()
    # First observation with an unknown label stores it as last regime.
    first = mem.observe("BTC", "NOT_A_REGIME")
    assert first.previous == "NONE"
    # Second observation: prev is stored but not a valid regime -> NONE branch.
    second = mem.observe("BTC", "COHERENT")
    assert second.previous == "NONE"
    assert second.current == "COHERENT"


def test_normal_transition_updates_matrix_and_surprise() -> None:
    mem = RegimeMemory(prior_count=1.0)
    mem.observe("ETH", "COHERENT")
    info = mem.observe("ETH", "METASTABLE")
    assert info.previous == "COHERENT"
    assert info.current == "METASTABLE"
    # With prior=1 and one increment: row = [1,2,1,1,1], total=6, prob=2/6.
    assert info.probability == round(2.0 / 6.0, 4)
    assert info.surprise == round(-math.log2(2.0 / 6.0), 4)


def test_transition_to_unknown_regime_uses_unknown_index() -> None:
    mem = RegimeMemory()
    mem.observe("XRP", "COHERENT")
    # An out-of-vocabulary target maps to the UNKNOWN column.
    info = mem.observe("XRP", "GIBBERISH")
    assert info.previous == "COHERENT"
    assert info.current == "GIBBERISH"
    # Probability mass landed on UNKNOWN index.
    p = mem.get_transition_probability("XRP", "COHERENT", "UNKNOWN")
    assert p > 0.0


def test_get_transition_probability_valid_and_invalid() -> None:
    mem = RegimeMemory()
    mem.observe("SOL", "COHERENT")
    mem.observe("SOL", "CRITICAL")
    valid = mem.get_transition_probability("SOL", "COHERENT", "CRITICAL")
    assert 0.0 < valid <= 1.0
    # Invalid from-regime.
    assert mem.get_transition_probability("SOL", "BAD", "CRITICAL") == 0.0
    # Invalid to-regime.
    assert mem.get_transition_probability("SOL", "COHERENT", "BAD") == 0.0


def test_get_transition_probability_zero_total_with_zero_prior() -> None:
    mem = RegimeMemory(prior_count=0.0)
    # No observations, prior 0 -> row sums to 0 -> the total==0 branch returns 0.
    assert mem.get_transition_probability("DOGE", "COHERENT", "CRITICAL") == 0.0


def test_get_expected_next_prefers_most_frequent() -> None:
    mem = RegimeMemory()
    for _ in range(5):
        mem.observe("ADA", "COHERENT")
        mem.observe("ADA", "METASTABLE")
    # Last regime is METASTABLE; expected-next is whatever row maximises.
    result = mem.get_expected_next("ADA")
    assert result in {
        "COHERENT",
        "METASTABLE",
        "DECOHERENT",
        "CRITICAL",
        "UNKNOWN",
    }


def test_get_expected_next_defaults_to_unknown_row() -> None:
    mem = RegimeMemory()
    # Never observed -> current defaults to UNKNOWN, row is uniform prior.
    assert mem.get_expected_next("NEW") == "COHERENT"


def test_pattern_exit_now() -> None:
    mem = RegimeMemory()
    mem.observe("BTC", "COHERENT")
    info = mem.observe("BTC", "CRITICAL")
    assert info.pattern == "EXIT_NOW"


def test_pattern_entry_setup() -> None:
    mem = RegimeMemory()
    mem.observe("BTC", "DECOHERENT")
    mem.observe("BTC", "METASTABLE")
    info = mem.observe("BTC", "COHERENT")
    assert info.pattern == "ENTRY_SETUP"


def test_pattern_none_when_no_match() -> None:
    mem = RegimeMemory()
    mem.observe("BTC", "COHERENT")
    mem.observe("BTC", "METASTABLE")
    info = mem.observe("BTC", "DECOHERENT")
    assert info.pattern is None
