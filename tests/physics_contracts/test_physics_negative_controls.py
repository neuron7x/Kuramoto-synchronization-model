# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the unified physics negative-control battery (Task 5).

The battery folds the four canonical controls into one ComparisonReport and
enforces two disciplines: a null failure can never yield SURVIVED_NULLS, and
synthetic data can never produce a real-data survival claim. ``n_null_draws`` is
recorded and an inadequate ensemble is rejected.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.falsification import SurrogateResult
from physics_contracts.manifold.negative_controls import (
    REQUIRED_CONTROLS,
    assemble_comparison_report,
    summarize_surrogate,
)

_REAL_FP = "b" * 64
_CONTROLS = {
    "time_shuffle": 0.20,
    "iaaft_surrogate": 0.25,
    "degree_preserving_rewire": 0.22,
    "causal_cutoff_violation": 0.30,
}


def test_real_data_survival_is_survived_nulls() -> None:
    report = assemble_comparison_report(
        candidate_statistic=0.5,
        control_statistics=_CONTROLS,
        n_null_draws=200,
        validity_domain="real",
        dataset_fingerprint=_REAL_FP,
    )
    assert report.survived_all_controls is True
    assert report.comparison.claim_status == "SURVIVED_NULLS"
    assert report.n_null_draws == 200


def test_synthetic_survival_is_downgraded() -> None:
    report = assemble_comparison_report(
        candidate_statistic=0.5,
        control_statistics=_CONTROLS,
        n_null_draws=200,
        validity_domain="synthetic",
        dataset_fingerprint="synthetic:00000001",
    )
    assert report.survived_all_controls is True
    # Survived on synthetic data — must not be a real-data survival claim.
    assert report.comparison.claim_status == "ARTIFACT_SUSPECTED"


def test_null_failure_downgrades_claim() -> None:
    report = assemble_comparison_report(
        candidate_statistic=0.21,  # below iaaft/rewire/cutoff controls
        control_statistics=_CONTROLS,
        n_null_draws=200,
        validity_domain="real",
        dataset_fingerprint=_REAL_FP,
    )
    assert report.survived_all_controls is False
    assert report.comparison.claim_status == "ARTIFACT_SUSPECTED"


def test_missing_control_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing required controls"):
        assemble_comparison_report(
            candidate_statistic=0.5,
            control_statistics={"time_shuffle": 0.2},
            n_null_draws=200,
            validity_domain="x",
            dataset_fingerprint=_REAL_FP,
        )


def test_unknown_control_is_rejected() -> None:
    bad = dict(_CONTROLS)
    bad["bogus_control"] = 0.1
    with pytest.raises(ValueError, match="unknown negative controls"):
        assemble_comparison_report(
            candidate_statistic=0.5,
            control_statistics=bad,
            n_null_draws=200,
            validity_domain="x",
            dataset_fingerprint=_REAL_FP,
        )


def test_inadequate_null_ensemble_is_rejected() -> None:
    with pytest.raises(ValueError, match="adequacy floor"):
        assemble_comparison_report(
            candidate_statistic=0.5,
            control_statistics=_CONTROLS,
            n_null_draws=10,
            validity_domain="x",
            dataset_fingerprint=_REAL_FP,
        )


def test_required_controls_are_the_four_canonical_ones() -> None:
    assert set(REQUIRED_CONTROLS) == {
        "time_shuffle",
        "iaaft_surrogate",
        "degree_preserving_rewire",
        "causal_cutoff_violation",
    }


def test_summarize_surrogate_reads_null_band() -> None:
    result = SurrogateResult(
        name="iaaft",
        observed=0.9,
        null_distribution=np.linspace(0.0, 1.0, 1001),
        p_value=0.01,
    )
    assert summarize_surrogate(result, quantile=0.95) == pytest.approx(0.95, abs=1e-3)


def test_summarize_surrogate_rejects_empty_null() -> None:
    result = SurrogateResult(
        name="iaaft",
        observed=0.9,
        null_distribution=np.asarray([], dtype=np.float64),
        p_value=1.0,
    )
    with pytest.raises(ValueError, match="empty null distribution"):
        summarize_surrogate(result)
