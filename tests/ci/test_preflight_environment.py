# SPDX-License-Identifier: MIT
"""ENV-009 preflight closure: POSITIVE (real env passes) + NEGATIVE (fail-closed).

The negative cases inject a doctored ``env_facts`` dict into the pure
:func:`evaluate` function and assert the gate refuses to pass *with the exact
exit code for that failure class*. This proves the pre-suite gatekeeper fails
closed with a class-specific code rather than failing open — without mutating
the real interpreter, uninstalling a dependency, or downgrading Python.
"""

from __future__ import annotations

import copy

from scripts.ci import preflight_environment as pe


def _facts() -> dict:
    """A live probe of the current environment (deep-copied per test)."""
    return copy.deepcopy(pe.probe_env_facts(pe.default_requirements()))


# --------------------------------------------------------------------------- #
# POSITIVE — the live interpreter satisfies the ENV-009 hard contract.
# --------------------------------------------------------------------------- #
def test_positive_current_env_passes() -> None:
    report = pe.evaluate(_facts(), pe.default_requirements())
    assert report["ok"], f"ENV-009 preflight unexpectedly FAILED: {report['failures']}"
    assert report["exit_code"] == pe.EXIT_PASS == 0
    assert not report["failures"]


def test_positive_main_exit_zero() -> None:
    assert pe.main([]) == 0


def test_positive_probe_shapes() -> None:
    facts = _facts()
    assert facts["python"]["major"] == 3
    assert "pandas" in facts["dependencies"]
    # git must be discoverable for the suite to run at all.
    assert facts["binaries"].get("git")


# --------------------------------------------------------------------------- #
# NEGATIVE — inject one fault at a time; assert the EXACT class + exit code.
# --------------------------------------------------------------------------- #
def test_negative_sub_floor_pandas() -> None:
    facts = _facts()
    facts["dependencies"]["pandas"] = "2.3.2"  # one patch below the 2.3.3 floor
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["PANDAS_FLOOR"] == 11
    assert report["failures"][0]["class"] == "PANDAS_FLOOR"


def test_negative_missing_pandas() -> None:
    facts = _facts()
    facts["dependencies"]["pandas"] = None
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == 11


def test_negative_missing_aiolimiter() -> None:
    facts = _facts()
    facts["dependencies"]["aiolimiter"] = None
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["MISSING_DEPENDENCY"] == 12
    assert any(
        f["class"] == "MISSING_DEPENDENCY" and "aiolimiter" in f["detail"]
        for f in report["failures"]
    )


def test_negative_missing_tenacity() -> None:
    facts = _facts()
    facts["dependencies"]["tenacity"] = None
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == 12
    assert any("tenacity" in f["detail"] for f in report["failures"])


def test_negative_python_39() -> None:
    facts = _facts()
    facts["python"] = {"major": 3, "minor": 9, "micro": 18}
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["PYTHON_RANGE"] == 10


def test_negative_python_313_upper_bound() -> None:
    facts = _facts()
    facts["python"] = {"major": 3, "minor": 13, "micro": 0}  # >= 3.13 is excluded
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == 10


def test_negative_forbidden_editable() -> None:
    facts = _facts()
    facts["editable_installs"] = {"geosync": "/some/rogue/path/outside/repo"}
    facts["allowed_editable_roots"] = ["/home/neuro7/GeoSync", "/home/neuro7/GeoSync-wt-w6"]
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["FORBIDDEN_EDITABLE"] == 17
    assert report["failures"][0]["class"] == "FORBIDDEN_EDITABLE"


def test_editable_inside_repo_is_allowed() -> None:
    facts = _facts()
    facts["editable_installs"] = {"geosync": "/home/neuro7/GeoSync/subpkg"}
    facts["allowed_editable_roots"] = ["/home/neuro7/GeoSync"]
    report = pe.evaluate(facts, pe.default_requirements())
    assert not any(f["class"] == "FORBIDDEN_EDITABLE" for f in report["failures"])


def test_negative_missing_git_binary() -> None:
    facts = _facts()
    facts["binaries"]["git"] = None
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["MISSING_BINARY"] == 16


def test_negative_bad_architecture() -> None:
    facts = _facts()
    facts["architecture"] = "riscv128"
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["ARCHITECTURE"] == 13


def test_negative_non_utf8_locale() -> None:
    facts = _facts()
    facts["locale_encoding"] = "ascii"
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["LOCALE"] == 14


def test_negative_missing_timezone() -> None:
    facts = _facts()
    facts["timezone"] = None
    report = pe.evaluate(facts, pe.default_requirements())
    assert not report["ok"]
    assert report["exit_code"] == pe.EXIT_CODES["TIMEZONE"] == 15


# --------------------------------------------------------------------------- #
# ADVISORY — disk/memory shortfalls are reported but MUST NOT stop the suite.
# --------------------------------------------------------------------------- #
def test_low_disk_is_advisory_only() -> None:
    facts = _facts()
    facts["free_disk_gb"] = 0.01
    facts["free_memory_gb"] = 0.01
    report = pe.evaluate(facts, pe.default_requirements())
    # Advisories are recorded...
    assert {a["class"] for a in report["advisories"]} >= {"DISK", "MEMORY"}
    # ...but do not, on their own, fail the gate.
    assert report["ok"]
    assert report["exit_code"] == 0


# --------------------------------------------------------------------------- #
# Exit-code determinism when multiple HARD classes fail at once.
# --------------------------------------------------------------------------- #
def test_multiple_failures_report_lowest_code() -> None:
    facts = _facts()
    facts["python"] = {"major": 3, "minor": 9, "micro": 0}  # PYTHON_RANGE (10)
    facts["dependencies"]["aiolimiter"] = None  # MISSING_DEPENDENCY (12)
    report = pe.evaluate(facts, pe.default_requirements())
    assert report["exit_code"] == 10  # the lowest / most-fundamental class wins
    assert len(report["failures"]) >= 2
