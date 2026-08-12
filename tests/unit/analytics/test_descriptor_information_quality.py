# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property + integration tests for descriptor information-quality measures.

Asserts the math (entropy at the uniform/degenerate extremes, JS divergence
bounds, monotonicity under concentration, distinguishability margin),
determinism, fail-closed behaviour, the descriptor-only claim stamp, and a
real composition with state_quantization + null_comparison.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from analytics.signals.descriptor_information_quality import (
    CLAIM_BOUNDARY,
    as_metadata,
    compute_information_quality,
)
from analytics.signals.null_comparison import compare_to_null
from analytics.signals.state_quantization import quantize_states

LABELS4 = ["a", "b", "c", "d"]


def _states(seq: list[int], labels: list[str]) -> list[str]:
    return [labels[i] for i in seq]


def test_uniform_distribution_is_max_entropy() -> None:
    states = _states(list(range(4)) * 1000, LABELS4)
    iq = compute_information_quality(states, states, labels=LABELS4, observed_percentile=50.0)
    assert math.isclose(iq.shannon_entropy_bits, math.log2(4), abs_tol=1e-9)
    assert math.isclose(iq.normalized_entropy, 1.0, abs_tol=1e-9)
    assert math.isclose(iq.effective_states, 4.0, abs_tol=1e-9)


def test_degenerate_distribution_is_zero_entropy() -> None:
    states = ["a"] * 500
    iq = compute_information_quality(states, states, labels=LABELS4, observed_percentile=50.0)
    assert math.isclose(iq.shannon_entropy_bits, 0.0, abs_tol=1e-12)
    assert math.isclose(iq.effective_states, 1.0, abs_tol=1e-12)
    assert math.isclose(iq.normalized_entropy, 0.0, abs_tol=1e-12)


def test_js_divergence_zero_for_identical_distributions() -> None:
    rng = np.random.default_rng(7)
    states = _states(rng.integers(0, 4, size=2000).tolist(), LABELS4)
    iq = compute_information_quality(states, states, labels=LABELS4, observed_percentile=50.0)
    assert math.isclose(iq.js_divergence_bits, 0.0, abs_tol=1e-9)


def test_js_divergence_one_bit_for_disjoint_supports() -> None:
    low = _states(([0, 1] * 500), LABELS4)
    high = _states(([2, 3] * 500), LABELS4)
    iq = compute_information_quality(low, high, labels=LABELS4, observed_percentile=99.0)
    assert math.isclose(iq.js_divergence_bits, 1.0, abs_tol=1e-9)


def test_entropy_monotone_under_concentration() -> None:
    spread = _states(list(range(4)) * 200, LABELS4)
    concentrated = ["a"] * 1500 + _states([1, 2, 3] * 50, LABELS4)
    h_spread = compute_information_quality(
        spread, spread, labels=LABELS4, observed_percentile=50.0
    ).shannon_entropy_bits
    h_conc = compute_information_quality(
        concentrated, concentrated, labels=LABELS4, observed_percentile=50.0
    ).shannon_entropy_bits
    assert h_conc < h_spread


@pytest.mark.parametrize("pct,expected", [(50.0, 0.0), (100.0, 1.0), (0.0, 1.0), (75.0, 0.5)])
def test_distinguishability_margin_from_percentile(pct: float, expected: float) -> None:
    states = ["a", "b", "c", "d"]
    iq = compute_information_quality(states, states, labels=LABELS4, observed_percentile=pct)
    assert math.isclose(iq.distinguishability, expected, abs_tol=1e-12)


def test_deterministic_for_equal_inputs() -> None:
    states = _states([0, 1, 2, 3, 0, 1], LABELS4)
    a = compute_information_quality(states, states, labels=LABELS4, observed_percentile=33.0)
    b = compute_information_quality(states, states, labels=LABELS4, observed_percentile=33.0)
    assert a == b


def test_empty_null_yields_zero_js_and_zero_effective_n() -> None:
    states = _states([0, 1, 2, 3], LABELS4)
    iq = compute_information_quality(states, [], labels=LABELS4, observed_percentile=50.0)
    assert iq.js_divergence_bits == 0.0
    assert iq.null_effective_n == 0


def test_single_label_vocabulary_normalized_entropy_is_zero() -> None:
    iq = compute_information_quality(["x", "x"], ["x"], labels=["x"], observed_percentile=50.0)
    assert iq.normalized_entropy == 0.0
    assert iq.n_states == 1


def test_fail_closed_empty_observed() -> None:
    with pytest.raises(ValueError):
        compute_information_quality([], ["a"], labels=LABELS4, observed_percentile=50.0)


def test_fail_closed_out_of_vocabulary_state() -> None:
    with pytest.raises(ValueError):
        compute_information_quality(["z"], ["a"], labels=LABELS4, observed_percentile=50.0)


def test_fail_closed_empty_vocabulary() -> None:
    with pytest.raises(ValueError):
        compute_information_quality(["a"], ["a"], labels=[], observed_percentile=50.0)


def test_fail_closed_duplicate_label() -> None:
    with pytest.raises(ValueError):
        compute_information_quality(["a"], ["a"], labels=["a", "a"], observed_percentile=50.0)


def test_fail_closed_percentile_out_of_range() -> None:
    with pytest.raises(ValueError):
        compute_information_quality(["a"], ["a"], labels=LABELS4, observed_percentile=150.0)


def test_claim_boundary_is_stamped() -> None:
    iq = compute_information_quality(["a", "b"], ["a"], labels=LABELS4, observed_percentile=10.0)
    assert iq.claim_boundary == CLAIM_BOUNDARY == "descriptor_only_not_predictor"
    assert iq.not_predictive_claim and iq.not_financial_advice and iq.research_only
    meta = as_metadata(iq)
    assert meta["claim_boundary"] == "descriptor_only_not_predictor"
    # as_metadata returns a read-only MappingProxyType; assignment must raise.
    # Route the mutation through an Any alias rather than a mypy suppression,
    # keeping the immutability assertion without growing the debt-ratchet count.
    frozen_meta: Any = meta
    with pytest.raises(TypeError):
        frozen_meta["claim_boundary"] = "x"


def test_integration_with_quantization_and_null_comparison() -> None:
    # Real composition: quantize a series and a null, locate the observed mean
    # within the null, and describe its information-quality. No invented data.
    labels = ["low", "mid", "high"]
    thresholds = [-0.5, 0.5]
    rng = np.random.default_rng(123)
    observed_values = rng.normal(0.0, 1.0, size=400).tolist()
    null_values = rng.normal(0.0, 1.0, size=4000)

    obs_states = quantize_states(observed_values, thresholds=thresholds, labels=labels).states
    null_states = quantize_states(null_values.tolist(), thresholds=thresholds, labels=labels).states

    cmp = compare_to_null(float(np.mean(observed_values)), null_values, band=0.05)

    iq = compute_information_quality(
        list(obs_states),
        list(null_states),
        labels=[*labels, "invalid"],  # quantize_states may emit the invalid label
        observed_percentile=cmp.percentile,
    )
    assert 0.0 <= iq.normalized_entropy <= 1.0
    assert 0.0 <= iq.js_divergence_bits <= 1.0 + 1e-9
    assert 0.0 <= iq.distinguishability <= 1.0
    assert iq.claim_boundary == "descriptor_only_not_predictor"
