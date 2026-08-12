# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed tests for the value-inference pipeline (issue #1293 capstone).

These tests lock the five integrated operations:

* **Falsify** — any broken stage is returned and blocks promotion;
* **Calibrate** — confidence aligns with support and fail-closes to 0 on any
  break; the temperature sharpens / damps confidence;
* **Normalize** — heterogeneous weights project onto the probability simplex,
  preserving proportions, with degenerate inputs handled explicitly;
* **Adapt** — the temperature tracks observed accuracy, is bounded, and leaves
  the structural falsification gate invariant;
* **Integrate** — the pipeline folds the four into one deterministic,
  fail-closed verdict that promotes only when nothing falsifies the claim and
  confidence clears the floor.

Each test fails if its guarantee is violated; together they are the executable
acceptance gate for the integration capstone.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from core.indicators.value_inference_pipeline import (
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    PIPELINE_CLAIM_BOUNDARY,
    BLOCKING_PIPELINE_STATUSES,
    Calibration,
    PipelineStatus,
    PipelineVerdict,
    StageVerdict,
    adapt,
    calibrate,
    falsify,
    normalize_weights,
    run_pipeline,
    stable_hash,
)

_MODULE_SOURCE = Path(inspect.getsourcefile(run_pipeline) or "").read_text(encoding="utf-8")


def _stage(
    name: str = "aggregation",
    *,
    passed: bool = True,
    support: float = 0.9,
    weight: float = 1.0,
) -> StageVerdict:
    return StageVerdict(name=name, passed=passed, support=support, weight=weight)


def _all_pass() -> list[StageVerdict]:
    return [
        _stage("normalization", support=0.95, weight=1.0),
        _stage("abstraction", support=0.90, weight=2.0),
        _stage("aggregation", support=0.85, weight=1.0),
    ]


# --- Нормалізувати / Normalize ---------------------------------------------


def test_normalize_weights_is_a_simplex() -> None:
    weights = normalize_weights(_all_pass())
    assert all(w >= 0.0 for w in weights)
    assert sum(weights) == pytest.approx(1.0)


def test_normalize_preserves_proportions() -> None:
    stages = [_stage("a", weight=2.0), _stage("b", weight=6.0)]
    w = normalize_weights(stages)
    assert w[1] == pytest.approx(3.0 * w[0])


def test_normalize_degenerate_zero_weights_is_uniform() -> None:
    stages = [_stage("a", weight=0.0), _stage("b", weight=0.0)]
    assert normalize_weights(stages) == (0.5, 0.5)


def test_normalize_empty_is_empty() -> None:
    assert normalize_weights([]) == ()


def test_normalize_rejects_negative_weight() -> None:
    with pytest.raises(ValueError, match="weight"):
        normalize_weights([_stage(weight=-1.0)])


def test_normalize_rejects_out_of_range_support() -> None:
    with pytest.raises(ValueError, match="support"):
        normalize_weights([_stage(support=1.5)])


# --- Фальсифікувати / Falsify ----------------------------------------------


def test_falsify_returns_broken_stages_only() -> None:
    stages = [_stage("ok", passed=True), _stage("bad", passed=False)]
    broken = falsify(stages)
    assert [s.name for s in broken] == ["bad"]


def test_falsify_empty_when_all_pass() -> None:
    assert falsify(_all_pass()) == ()


# --- Калібрувати / Calibrate -----------------------------------------------


def test_calibrate_fail_closes_to_zero_on_any_break() -> None:
    stages = [_stage("ok", passed=True, support=1.0), _stage("bad", passed=False, support=1.0)]
    weights = normalize_weights(stages)
    assert calibrate(stages, weights, Calibration()) == 0.0


def test_calibrate_identity_temperature_equals_weighted_support() -> None:
    stages = [_stage("a", support=0.8, weight=1.0), _stage("b", support=0.4, weight=1.0)]
    weights = normalize_weights(stages)
    # equal weights ⇒ mean support 0.6, temperature 1.0 ⇒ confidence == 0.6
    assert calibrate(stages, weights, Calibration(temperature=1.0)) == pytest.approx(0.6)


def test_calibrate_temperature_sharpens_confidence() -> None:
    stages = [_stage("a", support=0.5, weight=1.0)]
    weights = normalize_weights(stages)
    hot = calibrate(stages, weights, Calibration(temperature=4.0))
    cold = calibrate(stages, weights, Calibration(temperature=0.25))
    base = calibrate(stages, weights, Calibration(temperature=1.0))
    assert hot > base > cold


def test_calibrate_empty_is_zero() -> None:
    assert calibrate([], [], Calibration()) == 0.0


def test_calibrate_rejects_weight_length_mismatch() -> None:
    stages = _all_pass()
    with pytest.raises(ValueError, match="length"):
        calibrate(stages, [1.0], Calibration())


# --- Адаптувати / Adapt ----------------------------------------------------


def test_adapt_sharpens_when_underconfident() -> None:
    base = Calibration(temperature=1.0)
    adapted = adapt(base, observed_accuracy=0.9, predicted_confidence=0.5)
    assert adapted.temperature > base.temperature


def test_adapt_damps_when_overconfident() -> None:
    base = Calibration(temperature=1.0)
    adapted = adapt(base, observed_accuracy=0.4, predicted_confidence=0.9)
    assert adapted.temperature < base.temperature


def test_adapt_is_bounded() -> None:
    hot = adapt(Calibration(temperature=MAX_TEMPERATURE), 1.0, 0.0)
    cold = adapt(Calibration(temperature=MIN_TEMPERATURE), 0.0, 1.0)
    assert hot.temperature <= MAX_TEMPERATURE
    assert cold.temperature >= MIN_TEMPERATURE


def test_adapt_leaves_falsification_gate_invariant() -> None:
    # A pipeline broken by a failing stage stays DEMOTED no matter the temperature.
    stages = [_stage("ok", passed=True), _stage("bad", passed=False)]
    base = run_pipeline(stages, Calibration(temperature=1.0))
    adapted = adapt(Calibration(temperature=1.0), 1.0, 0.0)
    after = run_pipeline(stages, adapted)
    assert base.status is PipelineStatus.DEMOTED
    assert after.status is PipelineStatus.DEMOTED
    assert after.confidence == 0.0


def test_adapt_rejects_out_of_range_inputs() -> None:
    with pytest.raises(ValueError):
        adapt(Calibration(), observed_accuracy=1.5, predicted_confidence=0.5)
    with pytest.raises(ValueError):
        adapt(Calibration(), observed_accuracy=0.5, predicted_confidence=-0.1)


# --- Інтегрувати / Integrate -----------------------------------------------


def test_pipeline_integrates_when_all_pass() -> None:
    verdict = run_pipeline(_all_pass())
    assert verdict.status is PipelineStatus.INTEGRATED
    assert verdict.promoted is True
    assert verdict.confidence > 0.0
    assert verdict.falsifiers == ()


def test_pipeline_demotes_on_any_broken_stage() -> None:
    stages = _all_pass() + [_stage("value_target", passed=False, support=0.2)]
    verdict = run_pipeline(stages)
    assert verdict.status is PipelineStatus.DEMOTED
    assert verdict.promoted is False
    assert "value_target" in verdict.falsifiers
    assert verdict.confidence == 0.0


def test_pipeline_empty_is_not_run() -> None:
    verdict = run_pipeline([])
    assert verdict.status is PipelineStatus.NOT_RUN
    assert verdict.promoted is False
    assert PipelineStatus.NOT_RUN in BLOCKING_PIPELINE_STATUSES


def test_pipeline_min_confidence_floor_demotes_low_confidence() -> None:
    # All stages pass but support is weak; a confidence floor must demote.
    stages = [_stage("a", passed=True, support=0.3, weight=1.0)]
    verdict = run_pipeline(stages, min_confidence=0.8)
    assert verdict.status is PipelineStatus.DEMOTED
    assert "LOW_CONFIDENCE" in verdict.falsifiers


def test_pipeline_min_confidence_floor_allows_strong_support() -> None:
    stages = [_stage("a", passed=True, support=0.95, weight=1.0)]
    verdict = run_pipeline(stages, min_confidence=0.8)
    assert verdict.status is PipelineStatus.INTEGRATED


def test_pipeline_rejects_out_of_range_min_confidence() -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        run_pipeline(_all_pass(), min_confidence=2.0)


# --- determinism + boundary ------------------------------------------------


def test_pipeline_verdict_is_deterministic() -> None:
    a = run_pipeline(_all_pass())
    b = run_pipeline(_all_pass())
    assert a.provenance_hash == b.provenance_hash


def test_pipeline_hash_changes_with_stage_support() -> None:
    a = run_pipeline([_stage("a", support=0.9)])
    b = run_pipeline([_stage("a", support=0.8)])
    assert a.provenance_hash != b.provenance_hash


def test_stable_hash_is_order_independent() -> None:
    assert stable_hash({"x": 1, "y": 2}) == stable_hash({"y": 2, "x": 1})


def test_evidence_carries_claim_boundary_and_no_predictive_claim() -> None:
    verdict = run_pipeline(_all_pass())
    assert verdict.evidence["claim_boundary"] == PIPELINE_CLAIM_BOUNDARY
    assert verdict.evidence["not_predictive_claim"] is True


def test_verdict_to_dict_roundtrips() -> None:
    verdict = run_pipeline(_all_pass())
    payload = verdict.to_dict()
    assert payload["status"] == "INTEGRATED"
    assert payload["promoted"] is True
    assert isinstance(payload["falsifiers"], list)
    assert payload["provenance_hash"] == verdict.provenance_hash
    assert isinstance(verdict, PipelineVerdict)


# --- prose firewall: no product / forecast framing -------------------------


def test_no_forbidden_product_prose() -> None:
    folded = _MODULE_SOURCE.casefold()
    sanitized = folded.replace("value_inference_integration_only_not_predictor", "")
    sanitized = sanitized.replace("not_predictive_claim", "")
    forbidden = (
        r"trading signals?",
        r"\bpredictor\b(?!_)",
        r"\balpha\b",
        r"live[ -]trading",
        r"signal generation",
        r"predictive[ -]rank",
    )
    for pattern in forbidden:
        assert re.search(pattern, sanitized) is None, pattern
