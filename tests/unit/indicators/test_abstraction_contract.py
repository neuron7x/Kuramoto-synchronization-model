# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed tests for the abstraction contract (issue #1293).

These tests lock the abstraction-fidelity guarantees:

* every reduction step declares source/abstracted dimensions, a retained
  fraction, a fidelity floor, a known method, and a provenance hash;
* the validator fails closed on missing provenance, unknown methods,
  non-positive dimensions, and out-of-range fractions;
* a step is worth its cost only when it strictly compresses AND clears its
  fidelity floor; relabelling (ratio ≤ 1) demotes to NO_COMPRESSION and a
  below-floor reduction demotes to FIDELITY_LOSS;
* the content hash is deterministic and order-independent;
* the claim guard demotes every blocking status and the evidence bundle never
  asserts predictive rank.

Each test is constructed so it fails if the corresponding guarantee is
violated; together they form the executable acceptance gate for the
abstraction half of the issue.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from pathlib import Path

import pytest

from core.indicators.abstraction_contract import (
    ABSTRACTION_CLAIM_BOUNDARY,
    BLOCKING_ABSTRACTION_STATUSES,
    AbstractionArtifact,
    AbstractionGain,
    AbstractionStatus,
    abstraction_state_hash,
    compute_abstraction_gain,
    guard_abstraction_claim,
    stable_hash,
    validate_abstraction,
)

_MODULE_SOURCE = Path(inspect.getsourcefile(validate_abstraction) or "").read_text(
    encoding="utf-8"
)


def _artifact(
    name: str = "kuramoto_order_parameter",
    *,
    source_dim: int = 64,
    abstracted_dim: int = 1,
    retained_information: float = 0.92,
    fidelity_floor: float = 0.80,
    method: str = "order_parameter",
    provenance_hash: str = "deadbeef",
) -> AbstractionArtifact:
    return AbstractionArtifact(
        name=name,
        source_dim=source_dim,
        abstracted_dim=abstracted_dim,
        retained_information=retained_information,
        fidelity_floor=fidelity_floor,
        method=method,
        provenance_hash=provenance_hash,
    )


def _clean_set() -> list[AbstractionArtifact]:
    return [
        _artifact("kuramoto_order_parameter", source_dim=64, abstracted_dim=1),
        _artifact(
            "hurst_exponent",
            source_dim=512,
            abstracted_dim=1,
            method="fractal_exponent",
            retained_information=0.85,
        ),
    ]


# --- (1) artifact carries required fields ----------------------------------


def test_artifact_carries_required_fields() -> None:
    payload = _artifact().to_dict()
    for key in (
        "name",
        "source_dim",
        "abstracted_dim",
        "retained_information",
        "fidelity_floor",
        "method",
        "provenance_hash",
    ):
        assert key in payload


# --- (2) happy path: clean + compresses + clears floor ---------------------


def test_clean_compressing_faithful_set_is_abstracted() -> None:
    report = validate_abstraction(_clean_set())
    assert report.status is AbstractionStatus.ABSTRACTED
    assert report.ok
    assert not report.findings
    assert all(g.worth_cost for g in report.gains)
    card = guard_abstraction_claim(report)
    assert card.promoted is True


# --- (3) empty set ⇒ NOT_RUN, demoted --------------------------------------


def test_empty_set_is_not_run_and_blocks() -> None:
    report = validate_abstraction([])
    assert report.status is AbstractionStatus.NOT_RUN
    assert guard_abstraction_claim(report).promoted is False
    assert AbstractionStatus.NOT_RUN in BLOCKING_ABSTRACTION_STATUSES


# --- (4) per-step fail-closed findings -------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"provenance_hash": ""}, "MISSING_PROVENANCE_HASH"),
        ({"provenance_hash": "   "}, "MISSING_PROVENANCE_HASH"),
        ({"method": "magic"}, "UNKNOWN_METHOD"),
        ({"source_dim": 0}, "NONPOSITIVE_SOURCE_DIM"),
        ({"abstracted_dim": 0}, "NONPOSITIVE_ABSTRACTED_DIM"),
        ({"retained_information": 1.5}, "RETAINED_OUT_OF_RANGE"),
        ({"retained_information": -0.1}, "RETAINED_OUT_OF_RANGE"),
        ({"fidelity_floor": 2.0}, "FLOOR_OUT_OF_RANGE"),
    ],
)
def test_invalid_artifact_yields_partial(kwargs: dict[str, object], code: str) -> None:
    report = validate_abstraction([dataclasses.replace(_artifact(), **kwargs)])
    assert report.status is AbstractionStatus.PARTIAL
    assert any(f.code == code for f in report.findings)
    assert guard_abstraction_claim(report).promoted is False
    # PARTIAL short-circuits gain computation.
    assert report.gains == ()


# --- (5) compression is required -------------------------------------------


def test_no_compression_demotes() -> None:
    # source_dim == abstracted_dim ⇒ ratio == 1 ⇒ no compression.
    report = validate_abstraction([_artifact(source_dim=8, abstracted_dim=8)])
    assert report.status is AbstractionStatus.NO_COMPRESSION
    assert guard_abstraction_claim(report).promoted is False


def test_expansion_demotes_as_no_compression() -> None:
    report = validate_abstraction([_artifact(source_dim=4, abstracted_dim=16)])
    assert report.status is AbstractionStatus.NO_COMPRESSION


# --- (6) fidelity floor is required ----------------------------------------


def test_below_fidelity_floor_demotes() -> None:
    report = validate_abstraction(
        [_artifact(retained_information=0.50, fidelity_floor=0.80)]
    )
    assert report.status is AbstractionStatus.FIDELITY_LOSS
    assert guard_abstraction_claim(report).promoted is False


def test_exactly_at_floor_retains_fidelity() -> None:
    report = validate_abstraction(
        [_artifact(retained_information=0.80, fidelity_floor=0.80)]
    )
    assert report.status is AbstractionStatus.ABSTRACTED


def test_no_compression_takes_priority_over_fidelity_loss() -> None:
    # Both fail: ratio == 1 AND below floor. NO_COMPRESSION is reported first.
    report = validate_abstraction(
        [_artifact(source_dim=4, abstracted_dim=4, retained_information=0.1, fidelity_floor=0.9)]
    )
    assert report.status is AbstractionStatus.NO_COMPRESSION


def test_one_bad_step_demotes_whole_set() -> None:
    steps = _clean_set() + [_artifact("ricci_summary", retained_information=0.2, fidelity_floor=0.9)]
    report = validate_abstraction(steps)
    assert report.status is AbstractionStatus.FIDELITY_LOSS
    assert guard_abstraction_claim(report).promoted is False


# --- (7) compute_abstraction_gain semantics --------------------------------


def test_gain_ratio_and_flags() -> None:
    gain = compute_abstraction_gain(_artifact(source_dim=100, abstracted_dim=4))
    assert gain.compression_ratio == pytest.approx(25.0)
    assert gain.has_compression is True
    assert gain.retains_fidelity is True
    assert gain.worth_cost is True


def test_worth_cost_requires_both_flags_not_either() -> None:
    """`worth_cost = has_compression AND retains_fidelity` — never OR.

    The derived flag is invisible to the report-status tests (status is computed
    on a separate path), so this pins it directly. Each half-satisfied case must
    demote: under `And->Or` either one alone would wrongly promote worth_cost.
    """
    # compresses hard, but retained information is below the floor
    lossy = compute_abstraction_gain(
        _artifact(source_dim=100, abstracted_dim=4, retained_information=0.10, fidelity_floor=0.90)
    )
    assert lossy.has_compression is True
    assert lossy.retains_fidelity is False
    assert lossy.worth_cost is False

    # keeps fidelity, but does not actually compress (ratio == 1)
    flat = compute_abstraction_gain(
        _artifact(source_dim=8, abstracted_dim=8, retained_information=0.95, fidelity_floor=0.80)
    )
    assert flat.has_compression is False
    assert flat.retains_fidelity is True
    assert flat.worth_cost is False


def test_gain_is_dataclass_with_roundtrip() -> None:
    gain = compute_abstraction_gain(_artifact())
    assert isinstance(gain, AbstractionGain)
    payload = gain.to_dict()
    for key in ("compression_ratio", "has_compression", "retains_fidelity", "worth_cost"):
        assert key in payload


# --- (8) deterministic, order-independent hash -----------------------------


def test_state_hash_is_order_independent() -> None:
    steps = _clean_set()
    assert abstraction_state_hash(steps) == abstraction_state_hash(list(reversed(steps)))


def test_state_hash_changes_with_provenance() -> None:
    a = abstraction_state_hash([_artifact(provenance_hash="aaaa")])
    b = abstraction_state_hash([_artifact(provenance_hash="bbbb")])
    assert a != b


def test_stable_hash_is_deterministic() -> None:
    assert stable_hash({"x": 1, "y": 2}) == stable_hash({"y": 2, "x": 1})


# --- (9) evidence bundle carries the claim boundary ------------------------


def test_evidence_carries_claim_boundary_and_no_predictive_claim() -> None:
    report = validate_abstraction(_clean_set())
    assert report.evidence["claim_boundary"] == ABSTRACTION_CLAIM_BOUNDARY
    assert report.evidence["not_predictive_claim"] is True
    assert report.evidence["step_count"] == 2
    assert report.evidence["abstraction_hash"] == report.abstraction_hash


def test_report_to_dict_roundtrips() -> None:
    report = validate_abstraction(_clean_set())
    payload = report.to_dict()
    assert payload["status"] == "ABSTRACTED"
    assert payload["ok"] is True
    assert isinstance(payload["gains"], list)
    assert payload["abstraction_hash"] == report.abstraction_hash


# --- (10) prose firewall: no product / forecast framing --------------------


def test_no_forbidden_product_prose() -> None:
    folded = _MODULE_SOURCE.casefold()
    sanitized = folded.replace("abstraction_fidelity_only_not_predictor", "")
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
