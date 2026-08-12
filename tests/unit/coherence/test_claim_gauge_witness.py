# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync_hpc.coherence.claim_gauge_witness."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from geosync_hpc.coherence.claim_gauge_witness import (
    GaugeInput,
    GaugeStatus,
    GaugeWitness,
    assess_claim_gauge,
)


def _input(
    *,
    claim_id: str = "claim-test",
    local_constraints: tuple[str, ...] = ("a", "b", "c"),
    constraint_satisfaction: dict[str, bool] | None = None,
    required_constraints: tuple[str, ...] = ("a", "b", "c"),
) -> GaugeInput:
    if constraint_satisfaction is None:
        constraint_satisfaction = {"a": True, "b": True, "c": True}
    return GaugeInput(
        claim_id=claim_id,
        local_constraints=local_constraints,
        constraint_satisfaction=constraint_satisfaction,
        required_constraints=required_constraints,
    )


def test_all_required_satisfied_passes() -> None:
    """1. Every required constraint satisfied → GAUGE_PASS."""
    witness = assess_claim_gauge(_input())
    assert witness.status is GaugeStatus.GAUGE_PASS
    assert witness.failing_constraints == ()
    assert witness.missing_constraints == ()


def test_one_required_violated_refuses() -> None:
    """2. One required constraint reports False → GAUGE_REFUSED.

    This is the test the falsifier must break.
    """
    witness = assess_claim_gauge(
        _input(
            constraint_satisfaction={"a": True, "b": False, "c": True},
        )
    )
    assert witness.status is GaugeStatus.GAUGE_REFUSED
    assert "b" in witness.failing_constraints


def test_missing_required_constraint_unknown() -> None:
    """3. Required constraint missing from satisfaction map → UNKNOWN_CONSTRAINT."""
    witness = assess_claim_gauge(
        _input(
            constraint_satisfaction={"a": True, "c": True},  # b missing
        )
    )
    assert witness.status is GaugeStatus.UNKNOWN_CONSTRAINT
    assert "b" in witness.missing_constraints


def test_required_not_in_local_rejected() -> None:
    """4. required_constraints must be subset of local_constraints."""
    with pytest.raises(ValueError, match="not present in local_constraints"):
        GaugeInput(
            claim_id="x",
            local_constraints=("a",),
            constraint_satisfaction={"a": True},
            required_constraints=("a", "b"),
        )


def test_empty_required_rejected() -> None:
    with pytest.raises(ValueError, match="required_constraints must be non-empty"):
        GaugeInput(
            claim_id="x",
            local_constraints=("a",),
            constraint_satisfaction={"a": True},
            required_constraints=(),
        )


def test_empty_local_rejected() -> None:
    with pytest.raises(ValueError, match="local_constraints must be non-empty"):
        GaugeInput(
            claim_id="x",
            local_constraints=(),
            constraint_satisfaction={},
            required_constraints=("a",),
        )


def test_empty_claim_id_rejected() -> None:
    with pytest.raises(ValueError, match="claim_id must be a non-empty string"):
        GaugeInput(
            claim_id="",
            local_constraints=("a",),
            constraint_satisfaction={"a": True},
            required_constraints=("a",),
        )
    with pytest.raises(ValueError, match="claim_id must be a non-empty string"):
        GaugeInput(
            claim_id="   ",
            local_constraints=("a",),
            constraint_satisfaction={"a": True},
            required_constraints=("a",),
        )


def test_non_bool_satisfaction_rejected() -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        GaugeInput(
            claim_id="x",
            local_constraints=("a",),
            constraint_satisfaction={"a": 1},  # type: ignore[dict-item]
            required_constraints=("a",),
        )


def test_non_string_satisfaction_key_rejected() -> None:
    with pytest.raises(ValueError, match="constraint_satisfaction keys"):
        GaugeInput(
            claim_id="x",
            local_constraints=("a",),
            constraint_satisfaction={"": True},
            required_constraints=("a",),
        )


def test_non_tuple_local_rejected() -> None:
    with pytest.raises(TypeError, match="local_constraints must be a tuple"):
        GaugeInput(
            claim_id="x",
            local_constraints=["a"],  # type: ignore[arg-type]
            constraint_satisfaction={"a": True},
            required_constraints=("a",),
        )


def test_non_mapping_satisfaction_rejected() -> None:
    with pytest.raises(TypeError, match="must be a Mapping"):
        GaugeInput(
            claim_id="x",
            local_constraints=("a",),
            constraint_satisfaction=[("a", True)],  # type: ignore[arg-type]
            required_constraints=("a",),
        )


def test_empty_local_member_name_rejected() -> None:
    with pytest.raises(ValueError, match=r"local_constraints\[0\] must be a non-empty string"):
        GaugeInput(
            claim_id="x",
            local_constraints=("",),
            constraint_satisfaction={"": True},
            required_constraints=("",),
        )


def test_subset_required_passes() -> None:
    """Required can be a strict subset; non-required failures don't trip the gauge."""
    witness = assess_claim_gauge(
        _input(
            local_constraints=("a", "b", "c"),
            constraint_satisfaction={"a": True, "b": False, "c": True},
            required_constraints=("a", "c"),
        )
    )
    assert witness.status is GaugeStatus.GAUGE_PASS


def test_multiple_failures_listed_in_order() -> None:
    """failing_constraints preserves required-tuple order."""
    witness = assess_claim_gauge(
        _input(
            constraint_satisfaction={"a": False, "b": False, "c": True},
            required_constraints=("a", "b", "c"),
        )
    )
    assert witness.status is GaugeStatus.GAUGE_REFUSED
    assert witness.failing_constraints == ("a", "b")


def test_deterministic_repeated_calls_equal() -> None:
    inp = _input(
        constraint_satisfaction={"a": True, "b": False, "c": True},
        required_constraints=("a", "b", "c"),
    )
    a = assess_claim_gauge(inp)
    b = assess_claim_gauge(inp)
    assert a == b
    assert a.status is b.status
    assert a.evidence_fields == b.evidence_fields


def test_witness_is_frozen() -> None:
    witness = assess_claim_gauge(_input())
    with pytest.raises(Exception):  # noqa: B017
        witness.status = GaugeStatus.INVALID_INPUT  # type: ignore[misc]


def test_evidence_fields_immutable() -> None:
    witness = assess_claim_gauge(_input())
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]


def test_witness_carries_no_prediction_class_field() -> None:
    forbidden = {"prediction", "signal", "forecast", "target_price", "recommended_action"}
    fields = set(GaugeWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


def test_no_numeric_score_fields_exist() -> None:
    forbidden = {"score", "health_score", "health_index", "confidence", "percent", "ratio"}
    fields = set(GaugeWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


def test_falsifier_text_non_empty() -> None:
    witness = assess_claim_gauge(_input())
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "geosync_hpc" / "coherence" / "claim_gauge_witness.py"
)


def test_module_does_not_use_predictive_or_universal_language() -> None:
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden = (
        r"\bprediction\b",
        r"\buniversal\b",
        r"physical equivalence",
        r"new law of physics",
    )
    for pattern in forbidden:
        assert re.search(pattern, text) is None, f"forbidden phrase {pattern!r} present"


def test_module_does_not_import_market_or_trading_modules() -> None:
    text = _MODULE_PATH.read_text(encoding="utf-8")
    for tainted in (
        "from geosync_hpc.execution",
        "from geosync_hpc.policy",
        "from geosync_hpc.application",
    ):
        assert tainted not in text, f"{tainted!r} would couple this witness to runtime layers"
