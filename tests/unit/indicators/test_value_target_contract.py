# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed tests for the value-inference gates (issue #1293).

These tests lock the value-attribution guarantees:

* every run declares a value target (name, direction, unit, baseline policy);
* every signal declares a role and a standalone score;
* evidence gain is computed vs the best standalone module AND a null-fusion
  baseline, in a direction-aware way;
* the ablation report enumerates per-signal leave-one-in deltas;
* a claim demotes when gain is absent, when normalization is incomplete, or
  when no roles were declared;
* the one-command value report is deterministic and carries the claim
  boundary; it never asserts predictive rank.

Each test is constructed so it fails if the corresponding guarantee is
violated; together they form the executable acceptance gate for the issue.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from core.indicators.value_target_contract import (
    BLOCKING_VERDICTS,
    VALUE_CLAIM_BOUNDARY,
    AblationEntry,
    InferenceGain,
    InferenceVerdict,
    SignalRole,
    ValueDirection,
    ValueInferenceResult,
    ValueTarget,
    ablation_report,
    build_value_report,
    compute_inference_gain,
    compute_value_inference,
    stable_hash,
    value_report,
)

_MODULE_SOURCE = Path(inspect.getsourcefile(compute_value_inference) or "").read_text(
    encoding="utf-8"
)


def _target(
    direction: ValueDirection = ValueDirection.HIGHER_IS_BETTER,
) -> ValueTarget:
    return ValueTarget(
        name="fragility_separation",
        direction=direction,
        unit="auc",
        baseline_policy="best_single",
    )


def _roles() -> list[SignalRole]:
    return [
        SignalRole("ricci_field", "curvature_structure", 0.60),
        SignalRole("kuramoto_phase", "synchronization", 0.55),
        SignalRole("l2_liquidity", "depth_pressure", 0.50),
    ]


# --- (1) declared value target --------------------------------------------


def test_value_target_carries_required_fields() -> None:
    payload = _target().to_dict()
    for key in ("name", "direction", "unit", "baseline_policy"):
        assert key in payload
    assert payload["direction"] == "HIGHER_IS_BETTER"


# --- (2) role contract per signal -----------------------------------------


def test_signal_role_carries_role_and_standalone_score() -> None:
    role = SignalRole("ricci_field", "curvature_structure", 0.6)
    payload = role.to_dict()
    assert payload["role"] == "curvature_structure"
    assert payload["standalone_score"] == 0.6


# --- (3) evidence gain vs standalone + null-fusion ------------------------


def test_gain_present_when_fusion_beats_both() -> None:
    gain = compute_inference_gain(_target(), 0.9, _roles(), 0.40)
    assert isinstance(gain, InferenceGain)
    assert gain.has_gain is True
    assert gain.gain_over_standalone > 0
    assert gain.gain_over_null > 0


def test_gain_absent_when_fusion_ties_best_standalone() -> None:
    """Fusion no better than the best standalone module -> no gain."""

    gain = compute_inference_gain(_target(), 0.60, _roles(), 0.40)
    assert gain.has_gain is False


def test_gain_absent_when_fusion_ties_null_baseline() -> None:
    """Fusion equal to the null-fusion baseline -> no gain (no vacuous pass)."""

    gain = compute_inference_gain(_target(), 0.65, _roles(), 0.65)
    assert gain.has_gain is False


def test_gain_direction_aware_lower_is_better() -> None:
    """For a lower-is-better target, a smaller fused score is the gain."""

    target = _target(ValueDirection.LOWER_IS_BETTER)
    roles = [
        SignalRole("ricci_field", "curvature_structure", 0.30),
        SignalRole("kuramoto_phase", "synchronization", 0.40),
    ]
    # fused 0.10 < best standalone 0.30 and < null 0.50 -> gain present.
    gain = compute_inference_gain(target, 0.10, roles, 0.50)
    assert gain.has_gain is True
    # fused 0.35 > best standalone 0.30 -> worse -> no gain.
    worse = compute_inference_gain(target, 0.35, roles, 0.50)
    assert worse.has_gain is False


# --- (4) null-fusion baseline (explicit) ----------------------------------


def test_null_fusion_baseline_blocks_overclaim() -> None:
    """A null baseline matching the fused score must demote the claim."""

    result = compute_value_inference(_target(), 0.7, _roles(), 0.7)
    assert result.verdict is InferenceVerdict.DEMOTED_NO_GAIN
    assert result.promoted is False


# --- (5) ablation report --------------------------------------------------


def test_ablation_report_ranks_strongest_standalone_positive() -> None:
    entries = ablation_report(_target(), _roles())
    assert all(isinstance(e, AblationEntry) for e in entries)
    by_name = {e.name: e for e in entries}
    # ricci_field (0.60) is the strongest standalone -> positive delta.
    assert by_name["ricci_field"].delta_vs_best_other > 0
    # l2_liquidity (0.50) is the weakest -> non-positive delta.
    assert by_name["l2_liquidity"].delta_vs_best_other <= 0


# --- (6) claim demotion ----------------------------------------------------


def test_demotes_when_gain_absent() -> None:
    result = compute_value_inference(_target(), 0.60, _roles(), 0.40)
    assert result.verdict is InferenceVerdict.DEMOTED_NO_GAIN
    assert result.promoted is False


def test_demotes_when_normalization_incomplete() -> None:
    """Even with strong gain, incomplete upstream normalization demotes."""

    result = compute_value_inference(
        _target(), 0.95, _roles(), 0.40, normalization_ok=False
    )
    assert result.verdict is InferenceVerdict.DEMOTED_INCOMPLETE
    assert result.promoted is False


def test_not_run_when_no_roles_declared() -> None:
    result = compute_value_inference(_target(), 0.9, [], 0.4)
    assert result.verdict is InferenceVerdict.NOT_RUN
    assert result.promoted is False


def test_supported_only_with_gain_and_normalization() -> None:
    result = compute_value_inference(_target(), 0.95, _roles(), 0.40)
    assert result.verdict is InferenceVerdict.SUPPORTED
    assert result.promoted is True


@pytest.mark.parametrize(
    "verdict",
    [
        InferenceVerdict.DEMOTED_NO_GAIN,
        InferenceVerdict.DEMOTED_INCOMPLETE,
        InferenceVerdict.NOT_RUN,
    ],
)
def test_blocking_verdicts_are_non_promoting(verdict: InferenceVerdict) -> None:
    assert verdict in BLOCKING_VERDICTS
    assert InferenceVerdict.SUPPORTED not in BLOCKING_VERDICTS


# --- (7) one-command value report -----------------------------------------


def test_value_report_carries_boundary_and_is_deterministic() -> None:
    result = compute_value_inference(_target(), 0.95, _roles(), 0.40)
    report = value_report(result)
    assert report["claim_boundary"] == VALUE_CLAIM_BOUNDARY
    assert report["not_predictive_rank"] is True
    assert report["verdict"] == "SUPPORTED"
    assert "report_hash" in report
    # Determinism: identical run -> identical bytes.
    again = value_report(compute_value_inference(_target(), 0.95, _roles(), 0.40))
    assert report["report_hash"] == again["report_hash"]


def test_build_value_report_one_command() -> None:
    report = build_value_report(_target(), 0.60, _roles(), 0.40)
    assert report["verdict"] == "DEMOTED_NO_GAIN"
    assert report["promoted"] is False
    assert isinstance(report["ablation"], list)


def test_stable_hash_order_independent() -> None:
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})


# --- stress: seed/scale/window perturbation invariance ---------------------


def test_demotion_survives_score_perturbation_when_no_real_gain() -> None:
    """Nudging the fused score within the tolerance band must NOT manufacture
    a SUPPORTED verdict — demotion is robust to tiny perturbations."""

    base = compute_value_inference(_target(), 0.60, _roles(), 0.40)
    perturbed = compute_value_inference(_target(), 0.60 + 1e-12, _roles(), 0.40)
    assert base.verdict is InferenceVerdict.DEMOTED_NO_GAIN
    assert perturbed.verdict is InferenceVerdict.DEMOTED_NO_GAIN


# --- prose firewall: no predictive-rank / product claims -------------------


def test_no_forbidden_product_prose() -> None:
    folded = _MODULE_SOURCE.casefold()
    sanitized = folded.replace("value_attribution_only_not_predictive_rank", "")
    sanitized = sanitized.replace("not_predictive_rank", "")
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


def test_result_to_dict_roundtrips() -> None:
    result = compute_value_inference(_target(), 0.95, _roles(), 0.40)
    payload = result.to_dict()
    assert payload["verdict"] == "SUPPORTED"
    assert payload["promoted"] is True
    assert isinstance(payload["ablation"], list)
    assert isinstance(result, ValueInferenceResult)


def test_report_hash_excludes_itself_and_binds_the_body() -> None:
    """`stable_hash({k: v for ... if k != "report_hash"})` hashes the body MINUS its own hash.

    Under `NotEq -> Eq` the comprehension keeps only the `report_hash` key -- which is not yet
    in the body -- so every report hashes the empty dict to the SAME constant, destroying the
    integrity binding. Two materially different reports must therefore carry different hashes,
    and each hash must be reproducible over its body with the hash field removed.
    """
    from core.indicators.value_target_contract import build_value_report, stable_hash

    strong = build_value_report(_target(), 0.90, _roles(), 0.40)  # clear gain
    weak = build_value_report(_target(), 0.60, _roles(), 0.40)  # no gain

    assert strong["report_hash"] != weak["report_hash"], "different reports share a hash"

    recomputed = stable_hash({k: v for k, v in strong.items() if k != "report_hash"})
    assert recomputed == strong["report_hash"], "report_hash is not the hash of its own body"
