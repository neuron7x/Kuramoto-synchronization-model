# SPDX-License-Identifier: MIT
"""ENV-001 preflight closure: positive (real env passes) + negative (fail-closed).

The negative cases inject a doctored descriptor into the checker's pure
``evaluate_env`` input (a sub-2.3.3 pandas and a missing required dependency)
and assert the gate refuses to pass — proving the gatekeeper fails closed rather
than fails open.
"""

from __future__ import annotations

import copy

import pytest

from scripts.ci import check_env_preflight as cep


# --------------------------------------------------------------------------- #
# POSITIVE — the live interpreter satisfies the ENV-001 hard contract.
# --------------------------------------------------------------------------- #
def test_positive_current_env_passes() -> None:
    descriptor = cep.build_descriptor()
    ok, report = cep.evaluate_env(descriptor, cep.parse_required())
    assert ok, f"ENV-001 preflight unexpectedly FAILED on this env: {report['hard_failures']}"
    assert report["python_ok"], "interpreter is not Python 3.12"
    assert report["pandas_ok"], f"pandas {report['pandas_version']} below floor {cep.PANDAS_MIN}"
    assert not report["missing"], f"required deps missing: {report['missing']}"


def test_positive_main_exit_zero() -> None:
    assert cep.main([]) == 0


def test_descriptor_is_python_312() -> None:
    py = cep.build_descriptor()["python"]
    assert (py["major"], py["minor"]) == cep.REQUIRED_PYTHON


# --------------------------------------------------------------------------- #
# NEGATIVE — inject faults into the checker's input; gate must fail closed.
# --------------------------------------------------------------------------- #
def test_negative_sub_floor_pandas_fails_closed() -> None:
    descriptor = copy.deepcopy(cep.build_descriptor())
    descriptor["required_dependencies"]["resolved"]["pandas"] = "2.3.2"
    ok, report = cep.evaluate_env(descriptor, cep.parse_required())
    assert not ok, "sub-2.3.3 pandas must fail closed"
    assert not report["pandas_ok"]
    assert any("pandas" in hf for hf in report["hard_failures"])


def test_negative_missing_pandas_fails_closed() -> None:
    descriptor = copy.deepcopy(cep.build_descriptor())
    descriptor["required_dependencies"]["resolved"]["pandas"] = None
    ok, report = cep.evaluate_env(descriptor, cep.parse_required())
    assert not ok, "absent pandas must fail closed"
    assert any("pandas" in hf for hf in report["hard_failures"])


def test_negative_missing_required_dep_fails_closed() -> None:
    descriptor = copy.deepcopy(cep.build_descriptor())
    descriptor["required_dependencies"]["resolved"]["numpy"] = None
    ok, report = cep.evaluate_env(descriptor, cep.parse_required())
    assert not ok, "a missing required dependency must fail closed"
    assert "numpy" in report["missing"]
    assert any("numpy" in hf for hf in report["hard_failures"])


def test_negative_wrong_python_fails_closed() -> None:
    descriptor = copy.deepcopy(cep.build_descriptor())
    descriptor["python"]["major"] = 3
    descriptor["python"]["minor"] = 11
    ok, report = cep.evaluate_env(descriptor, cep.parse_required())
    assert not ok, "non-3.12 interpreter must fail closed"
    assert not report["python_ok"]


def test_strict_promotes_below_floor_to_hard_failure() -> None:
    """A below-floor dep is a non-fatal deviation by default, HARD under --strict."""
    descriptor = copy.deepcopy(cep.build_descriptor())
    # Force a below-floor deviation on a dep that is not the pandas gatekeeper.
    descriptor["required_dependencies"]["resolved"]["numpy"] = "0.0.1"
    ok_default, report_default = cep.evaluate_env(descriptor, cep.parse_required())
    ok_strict, report_strict = cep.evaluate_env(descriptor, cep.parse_required(), strict=True)
    assert {"name": "numpy", "installed": "0.0.1"}.items() <= (
        report_default["below_floor_deviations"][0].items()
    )
    assert not ok_strict, "strict mode must fail closed on any below-floor deviation"
    # Default mode: numpy present-but-old is a deviation, not a hard failure.
    assert not any("below floor (strict)" in hf for hf in report_default["hard_failures"])
    assert ok_default is (not report_default["hard_failures"])


def test_render_smoke() -> None:
    descriptor = cep.build_descriptor()
    _, report = cep.evaluate_env(descriptor, cep.parse_required())
    text = cep._render(report)
    assert "ENV-001 preflight" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
