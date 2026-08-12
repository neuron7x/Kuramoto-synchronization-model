# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""V(O) integral function tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from runtime.cognitive_bridge.value_function import (
    DEFAULT_WEIGHTS,
    GvCondition,
    ValueComponents,
    ValueWeights,
    integrate_value,
)


def _full_components(
    *,
    invariance: float = 1.0,
    falsifiability: float = 1.0,
    stability: float = 1.0,
    cross_domain: float = 1.0,
    actionability: float = 1.0,
    reproducibility: float = 1.0,
    productivity: float = 1.0,
    noise: float = 0.0,
    hallucination: float = 0.0,
    cognitive_cost: float = 0.0,
) -> ValueComponents:
    return ValueComponents(
        invariance=invariance,
        falsifiability=falsifiability,
        stability=stability,
        cross_domain=cross_domain,
        actionability=actionability,
        reproducibility=reproducibility,
        productivity=productivity,
        noise=noise,
        hallucination=hallucination,
        cognitive_cost=cognitive_cost,
    )


def _gv_pass() -> GvCondition:
    return GvCondition(
        has_falsification_contract=True,
        has_verification_evidence=True,
        completed_audit=True,
    )


def test_perfect_artifact_scores_at_positive_weight_sum() -> None:
    sample = _full_components()
    score = integrate_value((sample,), gv=_gv_pass())
    expected = (
        DEFAULT_WEIGHTS.alpha
        + DEFAULT_WEIGHTS.beta
        + DEFAULT_WEIGHTS.gamma
        + DEFAULT_WEIGHTS.delta
        + DEFAULT_WEIGHTS.epsilon
        + DEFAULT_WEIGHTS.zeta
        + DEFAULT_WEIGHTS.eta
    )
    assert score == pytest.approx(expected)


def test_zero_artifact_scores_zero() -> None:
    empty = ValueComponents(
        invariance=0,
        falsifiability=0,
        stability=0,
        cross_domain=0,
        actionability=0,
        reproducibility=0,
        productivity=0,
        noise=0,
        hallucination=0,
        cognitive_cost=0,
    )
    assert integrate_value((empty,), gv=_gv_pass()) == 0.0


def test_full_noise_artifact_scores_negative_normalised() -> None:
    noisy = ValueComponents(
        invariance=0.0,
        falsifiability=0.0,
        stability=0.0,
        cross_domain=0.0,
        actionability=0.0,
        reproducibility=0.0,
        productivity=0.0,
        noise=1.0,
        hallucination=1.0,
        cognitive_cost=1.0,
    )
    score = integrate_value((noisy,), gv=_gv_pass())
    expected = -(DEFAULT_WEIGHTS.lam + DEFAULT_WEIGHTS.mu + DEFAULT_WEIGHTS.nu)
    assert score == pytest.approx(expected)


def test_failing_gv_collapses_to_zero() -> None:
    sample = _full_components()
    gv = GvCondition(
        has_falsification_contract=False,
        has_verification_evidence=True,
        completed_audit=True,
    )
    assert integrate_value((sample,), gv=gv) == 0.0


def test_empty_samples_collapse_to_zero() -> None:
    assert integrate_value((), gv=_gv_pass()) == 0.0


def test_components_reject_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ValueComponents(
            invariance=1.5,
            falsifiability=0,
            stability=0,
            cross_domain=0,
            actionability=0,
            reproducibility=0,
            productivity=0,
            noise=0,
            hallucination=0,
            cognitive_cost=0,
        )


def test_value_weights_reject_inverted_priorities() -> None:
    with pytest.raises(ValueError):
        ValueWeights(
            alpha=0.01,
            beta=0.01,
            gamma=0.01,
            delta=0.01,
            epsilon=0.01,
            zeta=0.01,
            eta=0.01,
            lam=0.5,
            mu=0.5,
            nu=0.5,
        )


def test_value_weights_reject_negative_coefficients() -> None:
    with pytest.raises(ValueError):
        ValueWeights(alpha=-0.1)


def test_dt_must_be_positive() -> None:
    sample = _full_components()
    with pytest.raises(ValueError):
        integrate_value((sample,), gv=_gv_pass(), dt=0.0)


def test_normalisation_is_invariant_to_sample_count() -> None:
    sample = _full_components()
    one = integrate_value((sample,), gv=_gv_pass())
    five = integrate_value((sample,) * 5, gv=_gv_pass())
    assert one == pytest.approx(five)
