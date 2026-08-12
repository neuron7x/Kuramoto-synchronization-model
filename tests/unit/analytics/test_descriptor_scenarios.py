# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the deterministic descriptor scenario harness (Task 3).

Asserts every scenario runs reproducibly through the descriptor capsule, that
each regime shows its expected structural signature (degenerate -> zero
entropy, invalid -> counted invalid states, null_baseline -> near-zero JS
divergence), that the harness is deterministic, and that it stays strictly
descriptor-only (no trading/predictive semantics).
"""

from __future__ import annotations

import pytest

from analytics.signals.descriptor_scenarios import (
    SCENARIOS,
    run_all_scenarios,
    run_scenario,
)

EXPECTED = {"nominal", "noisy", "boundary", "degenerate", "invalid", "null_baseline"}


def test_catalogue_is_exactly_the_six_regimes() -> None:
    assert set(SCENARIOS) == EXPECTED


def test_run_all_is_deterministic() -> None:
    assert run_all_scenarios(seed=42) == run_all_scenarios(seed=42)


def test_each_scenario_runs_and_is_claim_safe() -> None:
    report = run_all_scenarios(seed=7)
    assert report["claim_boundary"] == "descriptor_only_not_predictor"
    for name in EXPECTED:
        rep = report["scenarios"][name]
        assert rep["claim_boundary"] == "descriptor_only_not_predictor"
        assert 0.0 <= rep["normalized_entropy"] <= 1.0
        assert 0.0 <= rep["js_divergence_bits"] <= 1.0 + 1e-9
        assert 0.0 <= rep["percentile"] <= 100.0
        assert len(rep["manifest_digest"]) == 64


def test_nominal_has_no_invalid_states() -> None:
    assert run_scenario("nominal", seed=3)["invalid_count"] == 0


def test_degenerate_collapses_entropy_to_zero() -> None:
    rep = run_scenario("degenerate", seed=3)
    assert rep["normalized_entropy"] == 0.0


def test_invalid_regime_counts_invalid_states() -> None:
    assert run_scenario("invalid", seed=3)["invalid_count"] > 0


def test_null_baseline_is_near_indistinguishable() -> None:
    # observed drawn from the same law as the null -> small JS divergence
    rep = run_scenario("null_baseline", seed=3)
    assert rep["js_divergence_bits"] < 0.05


def test_unknown_scenario_fails_closed() -> None:
    with pytest.raises(ValueError):
        run_scenario("does_not_exist", seed=1)


def test_distinct_seeds_give_distinct_nominal_digests() -> None:
    a = run_scenario("nominal", seed=1)["manifest_digest"]
    b = run_scenario("nominal", seed=2)["manifest_digest"]
    assert a != b
