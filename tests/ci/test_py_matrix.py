# SPDX-License-Identifier: MIT
"""ENV-002 matrix gate closure: positive (3.11 contract validates) + negatives.

The negatives inject a doctored contract into the gate's pure
``evaluate_contract`` input (a target of 3.9, and a missing required dependency)
and assert the gate refuses to pass — proving the matrix gate fails closed.

The honest note: this test does NOT execute a Python 3.11 interpreter. It
validates that the 3.11 CONTRACT matches the dependency policy and the declared
support window. The live 3.11 run is a leg of
``.github/workflows/python-matrix.yml`` (or ENV-005's hermetic image), not this
3.12 sandbox.
"""

from __future__ import annotations

import copy
import json

import pytest

from scripts.ci import check_py_matrix as cpm


# --------------------------------------------------------------------------- #
# POSITIVE — the committed 3.11 contract validates against policy.
# --------------------------------------------------------------------------- #
def test_positive_committed_contract_validates() -> None:
    descriptor = json.loads(cpm.CONTRACT_DEFAULT.read_text(encoding="utf-8"))
    ok, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert ok, f"3.11 contract unexpectedly FAILED: {report['hard_failures']}"
    assert report["target_supported"], "3.11 must be a declared supported leg"
    assert report["missing"] == [], f"contract missing deps: {report['missing']}"
    assert report["extra"] == [], f"contract has non-required deps: {report['extra']}"
    assert report["divergent_specifiers"] == [], report["divergent_specifiers"]


def test_positive_main_exit_zero() -> None:
    assert cpm.main(["--contract", str(cpm.CONTRACT_DEFAULT)]) == 0


def test_311_is_a_declared_supported_version() -> None:
    minors = cpm.supported_python_minors()
    assert (3, 11) in minors, f"pyproject must declare 3.11 as supported; got {minors}"
    assert (3, 12) in minors, "the 3.12 companion leg must also be declared"


def test_built_contract_matches_policy_by_construction() -> None:
    contract = cpm.build_contract((3, 11))
    ok, report = cpm.evaluate_contract(
        contract, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert ok, report["hard_failures"]
    assert report["contract_dep_count"] == report["policy_dep_count"] == 46


def test_contract_is_a_contract_not_a_live_run() -> None:
    """The 3.11 descriptor must NOT masquerade as a live resolution."""
    descriptor = json.loads(cpm.CONTRACT_DEFAULT.read_text(encoding="utf-8"))
    assert descriptor["kind"] == "contract"
    assert descriptor["resolution_status"] == "pending-matrix-ci"
    resolved = descriptor["required_dependencies"]["resolved"]
    assert all(v is None for v in resolved.values()), (
        "a CONTRACT must not carry fabricated resolved versions from a "
        "non-matching interpreter"
    )


# --------------------------------------------------------------------------- #
# NEGATIVE — inject faults; gate must fail closed.
# --------------------------------------------------------------------------- #
def test_negative_target_39_fails_closed() -> None:
    descriptor = copy.deepcopy(cpm.build_contract((3, 11)))
    descriptor["python"]["major"] = 3
    descriptor["python"]["minor"] = 9
    descriptor["python"]["target"] = "3.9.x"
    descriptor["required_dependencies"]["python_floor"] = "3.9"
    ok, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert not ok, "a 3.9 target outside the support window must fail closed"
    assert not report["target_supported"]
    assert any("3.9" in hf for hf in report["hard_failures"])


def test_negative_missing_required_dep_fails_closed() -> None:
    descriptor = copy.deepcopy(cpm.build_contract((3, 11)))
    del descriptor["required_dependencies"]["specifiers"]["numpy"]
    del descriptor["required_dependencies"]["resolved"]["numpy"]
    ok, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert not ok, "a missing required dependency must fail closed"
    assert "numpy" in report["missing"]
    assert any("numpy" in hf for hf in report["hard_failures"])


def test_negative_extra_dep_fails_closed() -> None:
    descriptor = copy.deepcopy(cpm.build_contract((3, 11)))
    descriptor["required_dependencies"]["specifiers"]["totally-not-a-dep"] = ">=1.0"
    ok, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert not ok, "a non-required dependency in the contract must fail closed"
    assert "totally-not-a-dep" in report["extra"]


def test_negative_specifier_divergence_fails_closed() -> None:
    descriptor = copy.deepcopy(cpm.build_contract((3, 11)))
    descriptor["required_dependencies"]["specifiers"]["numpy"] = ">=1.0.0"
    ok, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert not ok, "a mutated floor (version-specific divergence) must fail closed"
    assert any(d["name"] == "numpy" for d in report["divergent_specifiers"])


def test_negative_bad_pandas_floor_fails_closed() -> None:
    descriptor = copy.deepcopy(cpm.build_contract((3, 11)))
    descriptor["required_dependencies"]["pandas_floor"] = "2.0.0"
    ok, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert not ok, "a downgraded pandas floor must fail closed"
    assert any("pandas_floor" in hf for hf in report["hard_failures"])


def test_negative_resolved_out_of_policy_fails_closed() -> None:
    """If a live leg fills a resolved version that violates its floor, fail."""
    descriptor = copy.deepcopy(cpm.build_contract((3, 11)))
    descriptor["required_dependencies"]["resolved"]["numpy"] = "0.0.1"
    descriptor["resolution_status"] = "resolved-live"
    ok, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    assert not ok, "a resolved version below its own floor must fail closed"
    assert any(v["name"] == "numpy" for v in report["resolution_violations"])


def test_render_smoke() -> None:
    descriptor = cpm.build_contract((3, 11))
    _, report = cpm.evaluate_contract(
        descriptor, cpm.parse_required(), cpm.supported_python_minors()
    )
    text = cpm._render(report)
    assert "ENV-002 matrix contract gate" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
