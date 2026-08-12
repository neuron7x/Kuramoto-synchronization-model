# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync_hpc.coherence.global_parity_witness.

Cycle of falsification (per 7-link doctrine):

  CNS:          intuition that local pass does not imply global pass —
                a system can have all modules green while the global
                aggregation (claim ledger, deps, invariants, CI) is red.
  Exploration:  7-status decision tree where any failing required
                surface beats local pass; CI_GATE_UNKNOWN is its own
                failure branch.
  ЦШС artifact: LocalWitness / GlobalParityInput / GlobalParityWitness
                frozen dataclasses, pure deterministic
                assess_global_parity(...).
  Tests:        this file. Brief-required scenarios 1-16 covering all
                statuses, deterministic surface order, validation
                contract, structural decoupling, no-score guarantee.
  Falsifier:    ignoring dependency_truth_ok=False makes
                test_dependency_truth_failure fail.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from geosync_hpc.coherence.global_parity_witness import (
    GlobalParityInput,
    GlobalParityWitness,
    LocalWitness,
    assess_global_parity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANONICAL_REQUIRED: tuple[str, ...] = (
    "claim_ledger",
    "dependency_truth",
    "invariant_coverage",
    "ci_gate",
)


def _passing_local(name: str = "module_a") -> LocalWitness:
    return LocalWitness(
        name=name,
        passed=True,
        tier="ENGINEERING_ANALOG",
        reason="OK",
    )


def _failing_local(name: str = "module_b") -> LocalWitness:
    return LocalWitness(
        name=name,
        passed=False,
        tier="ENGINEERING_ANALOG",
        reason="local check failed",
    )


def _input(
    *,
    local_witnesses: tuple[LocalWitness, ...] | None = None,
    claim_ledger_ok: bool = True,
    dependency_truth_ok: bool = True,
    invariant_coverage_ok: bool = True,
    ci_gate_ok: bool | None = True,
    required_surfaces: tuple[str, ...] = CANONICAL_REQUIRED,
) -> GlobalParityInput:
    if local_witnesses is None:
        local_witnesses = (_passing_local("module_a"), _passing_local("module_b"))
    return GlobalParityInput(
        local_witnesses=local_witnesses,
        claim_ledger_ok=claim_ledger_ok,
        dependency_truth_ok=dependency_truth_ok,
        invariant_coverage_ok=invariant_coverage_ok,
        ci_gate_ok=ci_gate_ok,
        required_surfaces=required_surfaces,
    )


# ---------------------------------------------------------------------------
# Brief-required scenarios 1-7
# ---------------------------------------------------------------------------


def test_all_local_and_global_surfaces_pass() -> None:
    """1. all local + global surfaces pass → GLOBAL_PASS."""
    witness = assess_global_parity(_input())
    assert witness.status == "GLOBAL_PASS"
    assert witness.globally_consistent is True
    assert witness.failed_surfaces == ()
    assert witness.local_pass_count == 2
    assert witness.local_fail_count == 0


def test_one_local_witness_fails() -> None:
    """2. one local witness fails → LOCAL_FAILURE."""
    witness = assess_global_parity(
        _input(
            local_witnesses=(_passing_local("a"), _failing_local("b")),
        )
    )
    assert witness.status == "LOCAL_FAILURE"
    assert witness.globally_consistent is False
    assert "local:b" in witness.failed_surfaces
    assert witness.local_pass_count == 1
    assert witness.local_fail_count == 1


def test_claim_ledger_failure() -> None:
    """3. all local pass but claim ledger fails → CLAIM_LEDGER_FAILURE."""
    witness = assess_global_parity(_input(claim_ledger_ok=False))
    assert witness.status == "CLAIM_LEDGER_FAILURE"
    assert witness.globally_consistent is False
    assert witness.failed_surfaces == ("claim_ledger",)


def test_dependency_truth_failure() -> None:
    """4. all local pass but dependency truth fails → DEPENDENCY_TRUTH_FAILURE.

    This is the test the falsifier probe must break.
    """
    witness = assess_global_parity(_input(dependency_truth_ok=False))
    assert witness.status == "DEPENDENCY_TRUTH_FAILURE"
    assert witness.globally_consistent is False
    assert witness.failed_surfaces == ("dependency_truth",)


def test_invariant_coverage_failure() -> None:
    """5. all local pass but invariant coverage fails → INVARIANT_COVERAGE_FAILURE."""
    witness = assess_global_parity(_input(invariant_coverage_ok=False))
    assert witness.status == "INVARIANT_COVERAGE_FAILURE"
    assert witness.globally_consistent is False
    assert witness.failed_surfaces == ("invariant_coverage",)


def test_ci_gate_failure() -> None:
    """6. all local pass but CI False → CI_GATE_FAILURE."""
    witness = assess_global_parity(_input(ci_gate_ok=False))
    assert witness.status == "CI_GATE_FAILURE"
    assert witness.globally_consistent is False
    assert witness.failed_surfaces == ("ci_gate",)


def test_ci_gate_unknown() -> None:
    """7. all local pass but CI unknown → CI_GATE_UNKNOWN."""
    witness = assess_global_parity(_input(ci_gate_ok=None))
    assert witness.status == "CI_GATE_UNKNOWN"
    assert witness.globally_consistent is False
    assert witness.failed_surfaces == ("ci_gate",)


# ---------------------------------------------------------------------------
# Brief-required scenarios 8-12
# ---------------------------------------------------------------------------


def test_multiple_failures_deterministic_failed_surfaces_order() -> None:
    """8. multiple failures return deterministic failed_surfaces order.

    Locals (sorted by name) come first, then globals in canonical
    order: claim_ledger, dependency_truth, invariant_coverage, ci_gate.
    """
    locals_in = (
        _failing_local("zeta_module"),
        _passing_local("alpha_module"),
        _failing_local("beta_module"),
    )
    witness = assess_global_parity(
        _input(
            local_witnesses=locals_in,
            claim_ledger_ok=False,
            dependency_truth_ok=False,
            invariant_coverage_ok=False,
            ci_gate_ok=None,
        )
    )
    assert witness.failed_surfaces == (
        "local:beta_module",
        "local:zeta_module",
        "claim_ledger",
        "dependency_truth",
        "invariant_coverage",
        "ci_gate",
    )
    # Status is selected by priority — local failure wins.
    assert witness.status == "LOCAL_FAILURE"


def test_empty_local_witnesses_rejected() -> None:
    """9. empty local witnesses rejected at construction."""
    with pytest.raises(ValueError, match="local_witnesses must be non-empty"):
        GlobalParityInput(
            local_witnesses=(),
            claim_ledger_ok=True,
            dependency_truth_ok=True,
            invariant_coverage_ok=True,
            ci_gate_ok=True,
            required_surfaces=CANONICAL_REQUIRED,
        )


def test_empty_witness_name_rejected() -> None:
    """10. empty LocalWitness.name rejected at construction."""
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        LocalWitness(name="", passed=True, tier="ENGINEERING_ANALOG", reason="ok")
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        LocalWitness(name="   ", passed=True, tier="ENGINEERING_ANALOG", reason="ok")


def test_invalid_tier_rejected() -> None:
    """11. unknown tier string rejected.

    Valid tiers are exactly {FACT, ENGINEERING_ANALOG, HYPOTHESIS,
    SPECULATIVE} — anything else is a constructor failure.
    """
    with pytest.raises(ValueError, match="tier must be one of"):
        LocalWitness(
            name="x",
            passed=True,
            tier="MAGIC_TIER_NOT_IN_SET",
            reason="ok",
        )


def test_empty_reason_rejected() -> None:
    """12. empty / whitespace LocalWitness.reason rejected at construction."""
    with pytest.raises(ValueError, match="reason must be a non-empty string"):
        LocalWitness(
            name="x",
            passed=True,
            tier="ENGINEERING_ANALOG",
            reason="",
        )
    with pytest.raises(ValueError, match="reason must be a non-empty string"):
        LocalWitness(
            name="x",
            passed=True,
            tier="ENGINEERING_ANALOG",
            reason="   ",
        )


def test_witness_dataclass_frozen() -> None:
    """13. GlobalParityWitness is a frozen dataclass; assignment raises."""
    witness = assess_global_parity(_input())
    with pytest.raises(Exception):  # noqa: B017 — dataclasses raise FrozenInstanceError
        witness.globally_consistent = False  # type: ignore[misc]
    with pytest.raises(Exception):  # noqa: B017
        witness.status = "LOCAL_FAILURE"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Brief-required scenarios 14-17
# ---------------------------------------------------------------------------


def test_evidence_and_failed_surfaces_immutable() -> None:
    """14. evidence_fields and failed_surfaces are immutable."""
    witness = assess_global_parity(_input(claim_ledger_ok=False))
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]
    # failed_surfaces is a tuple (immutable by construction).
    assert isinstance(witness.failed_surfaces, tuple)


def test_no_forbidden_score_fields_exist() -> None:
    """15. no numeric health score / percent / confidence_float / health_index."""
    forbidden = {
        "score",
        "health_score",
        "health_index",
        "confidence",
        "confidence_float",
        "percent",
        "percentage",
        "ratio",
    }
    fields = set(GlobalParityWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(
        forbidden
    ), f"forbidden score fields present on witness: {fields & forbidden}"


def test_deterministic_repeated_calls_equal() -> None:
    """16. deterministic — repeated calls with identical inputs are equal."""
    inp = _input(
        local_witnesses=(
            _passing_local("a"),
            _failing_local("b"),
            _passing_local("c"),
        ),
        claim_ledger_ok=False,
        dependency_truth_ok=False,
    )
    a = assess_global_parity(inp)
    b = assess_global_parity(inp)
    assert a == b
    assert a.status == b.status
    assert a.failed_surfaces == b.failed_surfaces
    assert a.evidence_fields == b.evidence_fields


_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "geosync_hpc" / "coherence" / "global_parity_witness.py"
)


def test_no_imports_from_execution_policy_application_layers() -> None:
    """17. no imports from execution / policy / application layers."""
    text = _MODULE_PATH.read_text(encoding="utf-8")
    for tainted in (
        "from geosync_hpc.execution",
        "from geosync_hpc.policy",
        "from geosync_hpc.application",
        "import geosync_hpc.execution",
        "import geosync_hpc.policy",
        "import geosync_hpc.application",
    ):
        assert tainted not in text, f"{tainted!r} would couple this witness to runtime layers"


# ---------------------------------------------------------------------------
# Auxiliary structural / priority tests
# ---------------------------------------------------------------------------


def test_priority_local_failure_beats_global_failure() -> None:
    """LOCAL_FAILURE wins over CLAIM_LEDGER_FAILURE for status selection."""
    witness = assess_global_parity(
        _input(
            local_witnesses=(_failing_local("x"),),
            claim_ledger_ok=False,
        )
    )
    assert witness.status == "LOCAL_FAILURE"


def test_priority_claim_beats_dependency_beats_invariant_beats_ci() -> None:
    """When multiple globals fail, claim_ledger > dependency_truth > invariant > ci."""
    witness = assess_global_parity(
        _input(
            claim_ledger_ok=False,
            dependency_truth_ok=False,
            invariant_coverage_ok=False,
            ci_gate_ok=False,
        )
    )
    assert witness.status == "CLAIM_LEDGER_FAILURE"


def test_dependency_status_when_claim_passes() -> None:
    """With claim OK and dependency failing, status == DEPENDENCY_TRUTH_FAILURE."""
    witness = assess_global_parity(
        _input(
            dependency_truth_ok=False,
            invariant_coverage_ok=False,
            ci_gate_ok=False,
        )
    )
    assert witness.status == "DEPENDENCY_TRUTH_FAILURE"


def test_required_surfaces_can_be_subset() -> None:
    """If a surface is not required, its False value does not flip the verdict."""
    witness = assess_global_parity(
        _input(
            ci_gate_ok=None,
            required_surfaces=("claim_ledger", "dependency_truth", "invariant_coverage"),
        )
    )
    assert witness.status == "GLOBAL_PASS"
    assert witness.globally_consistent is True


def test_required_surfaces_unknown_name_rejected() -> None:
    """A required-surfaces entry that is not a canonical name is rejected."""
    with pytest.raises(ValueError, match="unknown surface"):
        GlobalParityInput(
            local_witnesses=(_passing_local("a"),),
            claim_ledger_ok=True,
            dependency_truth_ok=True,
            invariant_coverage_ok=True,
            ci_gate_ok=True,
            required_surfaces=("not_a_real_surface",),
        )


def test_required_surfaces_empty_string_rejected() -> None:
    """Empty / whitespace required-surfaces entries are rejected."""
    with pytest.raises(ValueError, match="non-empty strings"):
        GlobalParityInput(
            local_witnesses=(_passing_local("a"),),
            claim_ledger_ok=True,
            dependency_truth_ok=True,
            invariant_coverage_ok=True,
            ci_gate_ok=True,
            required_surfaces=("",),
        )


def test_input_local_witnesses_must_be_tuple() -> None:
    with pytest.raises(TypeError, match="local_witnesses must be a tuple"):
        GlobalParityInput(
            local_witnesses=[_passing_local("a")],  # type: ignore[arg-type]
            claim_ledger_ok=True,
            dependency_truth_ok=True,
            invariant_coverage_ok=True,
            ci_gate_ok=True,
            required_surfaces=CANONICAL_REQUIRED,
        )


def test_input_local_witness_must_be_localwitness() -> None:
    with pytest.raises(TypeError, match="must be a LocalWitness"):
        GlobalParityInput(
            local_witnesses=("not_a_witness",),  # type: ignore[arg-type]
            claim_ledger_ok=True,
            dependency_truth_ok=True,
            invariant_coverage_ok=True,
            ci_gate_ok=True,
            required_surfaces=CANONICAL_REQUIRED,
        )


def test_canonical_surfaces_classmethod_returns_expected() -> None:
    assert GlobalParityInput.canonical_surfaces() == (
        "claim_ledger",
        "dependency_truth",
        "invariant_coverage",
        "ci_gate",
    )


def test_witness_falsifier_text_non_empty() -> None:
    witness = assess_global_parity(_input())
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


def test_evidence_fields_carry_decision_inputs() -> None:
    inp = _input(
        local_witnesses=(_passing_local("a"), _failing_local("b")),
        claim_ledger_ok=False,
        dependency_truth_ok=True,
        invariant_coverage_ok=True,
        ci_gate_ok=True,
    )
    witness = assess_global_parity(inp)
    ev = witness.evidence_fields
    assert ev["local_count"] == 2
    assert ev["local_pass_count"] == 1
    assert ev["local_fail_count"] == 1
    assert ev["claim_ledger_ok"] is False
    assert ev["dependency_truth_ok"] is True
    assert ev["ci_gate_ok"] is True
    assert "local:b" in ev["failed_surfaces"]
    assert "claim_ledger" in ev["failed_surfaces"]
