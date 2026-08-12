# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-control coverage and FPR threshold."""

from __future__ import annotations

import numpy as np
import pytest

from instrument_validation.negative_control import (
    REQUIRED_NULLS,
    gen_configuration_double_swap,
    gen_constant_node_panel,
    gen_erdos_renyi,
    gen_low_n_correlation_pair,
    run_negative_controls,
)


def _trivial_zero_score(adjacency: np.ndarray) -> float:
    return 0.0


def _trivial_high_score(adjacency: np.ndarray) -> float:
    return 1.0


def test_required_nulls_complete() -> None:
    assert set(REQUIRED_NULLS) == {
        "erdos_renyi_density_matched",
        "configuration_model_uniform_double_swap",
        "low_n_correlation_saturation",
        "constant_node_zero_strength",
    }


def test_run_negative_controls_passes_for_zero_score() -> None:
    cert = run_negative_controls(
        _trivial_zero_score,
        instrument_id="zero@v0",
        n_runs=500,
        decision_threshold=0.5,
    )
    assert cert.passed
    for fam in REQUIRED_NULLS:
        assert fam in cert.fpr_per_family
    assert cert.max_observed_fpr <= 0.05


def test_run_negative_controls_fails_for_always_positive_score() -> None:
    cert = run_negative_controls(
        _trivial_high_score,
        instrument_id="always_positive@v0",
        n_runs=500,
        decision_threshold=0.5,
    )
    assert not cert.passed
    assert cert.max_observed_fpr > 0.05
    assert cert.failure_reason is not None


def test_run_negative_controls_rejects_low_n_runs() -> None:
    with pytest.raises(ValueError, match="< required"):
        run_negative_controls(
            _trivial_zero_score,
            instrument_id="x",
            n_runs=10,
            decision_threshold=0.5,
        )


def test_generators_produce_correct_shapes() -> None:
    er = gen_erdos_renyi(seed=1, n=20, n_edges=40)
    assert er.shape == (20, 20)
    cm = gen_configuration_double_swap(seed=1, n=20, degree_sequence=[4] * 20)
    assert cm.shape == (20, 20)
    ln = gen_low_n_correlation_pair(seed=1, n_obs=3, n_pairs=10)
    assert 0 <= ln.size <= 10
    cn = gen_constant_node_panel(seed=1, n_nodes=15, n_quarters=6)
    assert cn.shape == (6, 15)
