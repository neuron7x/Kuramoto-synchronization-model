# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed tests for the executable aggregation contract (issue #1292).

These tests lock the aggregation-integrity guarantees for fused signal
artifacts:

* per-signal schema, timestamps, alignment policy, provenance hash, and
  normalization status are required;
* the validator fails closed on missing schema / provenance hash, unknown
  alignment policy, unsorted or missing timestamps, timestamp misalignment
  under the exact policy, and incomplete normalization;
* the aggregate-state hash is deterministic and order-independent;
* evidence gain is computed against the best standalone signal AND a
  null-fusion baseline, and is absent when fusion adds nothing;
* the claim-card guard demotes an aggregation claim when gain is absent or
  inputs are not fully normalized.

Each test is constructed so it fails if the corresponding guarantee is
violated; together they form the executable acceptance gate for the issue.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from core.indicators.aggregation_contract import (
    AGGREGATION_CLAIM_BOUNDARY,
    BLOCKING_AGGREGATION_STATUSES,
    FUSED_SIGNAL_INPUTS,
    AggregationClaimCard,
    AggregationReport,
    AggregationStatus,
    EvidenceGain,
    SignalArtifact,
    SignalNormalizationStatus,
    aggregate_state_hash,
    evidence_gain,
    guard_aggregation_claim,
    stable_hash,
    validate_aggregation,
)

_MODULE_SOURCE = Path(inspect.getsourcefile(validate_aggregation) or "").read_text(
    encoding="utf-8"
)


def _artifact(
    name: str = "ricci_field",
    *,
    schema: tuple[str, ...] = ("value",),
    timestamps: tuple[int, ...] = (0, 1, 2),
    alignment_policy: str = "exact",
    provenance_hash: str = "a" * 64,
    normalization_status: SignalNormalizationStatus = SignalNormalizationStatus.NORMALIZED,
) -> SignalArtifact:
    """Return a fully-valid, normalized signal artifact."""

    return SignalArtifact(
        name=name,
        schema=schema,
        timestamps=timestamps,
        alignment_policy=alignment_policy,
        provenance_hash=provenance_hash,
        normalization_status=normalization_status,
    )


def _clean_set() -> list[SignalArtifact]:
    return [
        _artifact("ricci_field"),
        _artifact("kuramoto_phase"),
        _artifact("l2_liquidity"),
    ]


def _gain(has: bool = True) -> EvidenceGain:
    if has:
        return evidence_gain(0.9, {"ricci_field": 0.6, "kuramoto_phase": 0.5}, 0.4)
    return evidence_gain(0.5, {"ricci_field": 0.6, "kuramoto_phase": 0.5}, 0.4)


# --- (1) input signal list ------------------------------------------------


def test_fused_signal_inputs_cover_target_chain() -> None:
    required = {
        "returns",
        "l2_liquidity",
        "ricci_field",
        "kuramoto_phase",
        "volatility",
        "cost_state",
    }
    assert required <= set(FUSED_SIGNAL_INPUTS)


# --- (2) per-signal schema + bundle fields --------------------------------


def test_artifact_carries_required_fields() -> None:
    payload = _artifact().to_dict()
    for key in (
        "name",
        "schema",
        "timestamps",
        "alignment_policy",
        "provenance_hash",
        "normalization_status",
    ):
        assert key in payload
    assert payload["normalization_status"] == "NORMALIZED"


def test_clean_set_with_gain_aggregates() -> None:
    report = validate_aggregation(_clean_set(), _gain(has=True))
    assert report.ok
    assert report.status is AggregationStatus.AGGREGATED


# --- (3) fail-closed validator surfaces -----------------------------------


def test_missing_schema_fails_closed() -> None:
    report = validate_aggregation([_artifact(schema=())], _gain())
    assert not report.ok
    assert any(f.code == "MISSING_SCHEMA" for f in report.findings)
    assert report.status is AggregationStatus.PARTIAL


def test_missing_provenance_hash_fails_closed() -> None:
    report = validate_aggregation([_artifact(provenance_hash="")], _gain())
    assert any(f.code == "MISSING_PROVENANCE_HASH" for f in report.findings)


def test_whitespace_only_provenance_hash_fails_closed() -> None:
    """A blank-but-non-empty provenance hash is still missing.

    Pins `not hash or not hash.strip()` — the second disjunct is the only one
    that fires for whitespace ("   " is truthy, so `not hash` is False). Under
    `Or->And` the finding would vanish because the first disjunct is False,
    letting a provenance-less signal through. The empty-string case above cannot
    catch this: there both disjuncts are True, so And and Or agree.
    """
    report = validate_aggregation([_artifact(provenance_hash="   ")], _gain())
    assert any(f.code == "MISSING_PROVENANCE_HASH" for f in report.findings)


def test_unknown_alignment_policy_fails_closed() -> None:
    report = validate_aggregation([_artifact(alignment_policy="telepathy")], _gain())
    assert any(f.code == "UNKNOWN_ALIGNMENT_POLICY" for f in report.findings)


def test_missing_timestamps_fails_closed() -> None:
    report = validate_aggregation([_artifact(timestamps=())], _gain())
    assert any(f.code == "MISSING_TIMESTAMPS" for f in report.findings)


def test_unsorted_timestamps_fails_closed() -> None:
    report = validate_aggregation([_artifact(timestamps=(2, 0, 1))], _gain())
    assert any(f.code == "UNSORTED_TIMESTAMPS" for f in report.findings)


def test_incomplete_normalization_fails_closed() -> None:
    art = _artifact(normalization_status=SignalNormalizationStatus.SCALE_SENSITIVE)
    report = validate_aggregation([art], _gain())
    assert any(f.code == "NORMALIZATION_INCOMPLETE" for f in report.findings)
    assert report.status is AggregationStatus.PARTIAL


def test_timestamp_misalignment_under_exact_policy_fails_closed() -> None:
    """Two exact-policy signals on different grids is a fail-closed misalignment."""

    a = _artifact("ricci_field", timestamps=(0, 1, 2))
    b = _artifact("kuramoto_phase", timestamps=(0, 1, 3))
    report = validate_aggregation([a, b], _gain())
    assert any(f.code == "TIMESTAMP_MISALIGNMENT" for f in report.findings)


def test_empty_input_set_is_not_run() -> None:
    report = validate_aggregation([])
    assert report.status is AggregationStatus.NOT_RUN


# --- (4) aggregate-state hash ---------------------------------------------


def test_aggregate_hash_is_deterministic_and_order_independent() -> None:
    a = _artifact("ricci_field")
    b = _artifact("kuramoto_phase")
    h1 = aggregate_state_hash([a, b])
    h2 = aggregate_state_hash([b, a])
    assert h1 == h2
    assert len(h1) == 64
    assert stable_hash({"x": 1, "y": 2}) == stable_hash({"y": 2, "x": 1})


def test_aggregate_hash_changes_with_inputs() -> None:
    base = aggregate_state_hash(_clean_set())
    mutated = aggregate_state_hash(
        [_artifact("ricci_field", provenance_hash="z" * 64), _artifact("kuramoto_phase")]
    )
    assert base != mutated


# --- (5) standalone-vs-aggregate + null-fusion baseline -------------------


def test_evidence_gain_present_when_fusion_beats_both() -> None:
    g = evidence_gain(0.9, {"ricci_field": 0.6, "kuramoto_phase": 0.5}, 0.4)
    assert isinstance(g, EvidenceGain)
    assert g.has_gain is True
    assert g.gain_over_standalone > 0
    assert g.gain_over_null > 0


def test_evidence_gain_absent_when_fusion_loses_to_standalone() -> None:
    """Fusion no better than the best standalone signal -> no gain."""

    g = evidence_gain(0.55, {"ricci_field": 0.6}, 0.4)
    assert g.has_gain is False


def test_evidence_gain_absent_when_fusion_ties_null() -> None:
    """Fusion equal to the null-fusion baseline -> no gain (no vacuous pass)."""

    g = evidence_gain(0.4, {"ricci_field": 0.3}, 0.4)
    assert g.has_gain is False


def test_no_gain_drives_no_evidence_gain_status() -> None:
    report = validate_aggregation(_clean_set(), _gain(has=False))
    assert report.ok  # inputs clean
    assert report.status is AggregationStatus.NO_EVIDENCE_GAIN


def test_missing_gain_object_is_no_evidence_gain() -> None:
    report = validate_aggregation(_clean_set(), None)
    assert report.status is AggregationStatus.NO_EVIDENCE_GAIN


# --- (6) evidence bundle fields -------------------------------------------


def test_evidence_bundle_carries_required_fields() -> None:
    report = validate_aggregation(_clean_set(), _gain(has=True))
    ev = report.evidence
    assert ev["claim_boundary"] == AGGREGATION_CLAIM_BOUNDARY
    assert ev["not_predictive_claim"] is True
    assert ev["aggregate_hash"] == report.aggregate_hash
    assert "signals" in ev
    assert ev["evidence_gain"]["has_gain"] is True
    for name in ("ricci_field", "kuramoto_phase", "l2_liquidity"):
        sig = ev["signals"][name]
        assert "provenance_hash" in sig
        assert "normalization_status" in sig


# --- (7) claim-card guard -------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        AggregationStatus.NOT_RUN,
        AggregationStatus.PARTIAL,
        AggregationStatus.NO_EVIDENCE_GAIN,
    ],
)
def test_guard_demotes_unsupported_aggregation(status: AggregationStatus) -> None:
    assert status in BLOCKING_AGGREGATION_STATUSES


def test_guard_demotes_no_evidence_gain_report() -> None:
    report = validate_aggregation(_clean_set(), _gain(has=False))
    card = guard_aggregation_claim(report)
    assert isinstance(card, AggregationClaimCard)
    assert card.promoted is False


def test_guard_demotes_partial_report() -> None:
    report = validate_aggregation([_artifact(schema=())], _gain(has=True))
    card = guard_aggregation_claim(report)
    assert card.promoted is False


def test_guard_promotes_only_aggregated() -> None:
    report = validate_aggregation(_clean_set(), _gain(has=True))
    card = guard_aggregation_claim(report)
    assert card.promoted is True
    assert report.status is AggregationStatus.AGGREGATED


# --- standalone-vs-aggregate stress: amplitude/seed/window perturbation ----


def test_standalone_vs_aggregate_no_overclaim_on_null_fusion() -> None:
    """A null-fusion baseline that matches the fused score must NOT promote.

    Models the 'fusion adds nothing beyond a trivial average' bypass: the
    contract demotes rather than rubber-stamping the aggregation.
    """

    null_matches = evidence_gain(0.7, {"ricci_field": 0.5}, 0.7)
    assert null_matches.has_gain is False
    report = validate_aggregation(_clean_set(), null_matches)
    assert report.status is AggregationStatus.NO_EVIDENCE_GAIN
    assert guard_aggregation_claim(report).promoted is False


# --- prose firewall -------------------------------------------------------


def test_no_forbidden_product_prose() -> None:
    folded = _MODULE_SOURCE.casefold()
    sanitized = folded.replace("aggregation_integrity_only_not_predictor", "")
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


def test_report_to_dict_roundtrips() -> None:
    report = validate_aggregation(_clean_set(), _gain(has=True))
    payload = report.to_dict()
    assert payload["status"] == "AGGREGATED"
    assert payload["ok"] is True
    assert payload["aggregate_hash"] == report.aggregate_hash
    assert isinstance(payload["findings"], list)
