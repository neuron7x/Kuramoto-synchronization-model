# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contracts for the governance-tooling coverage profile.

tools/ and scripts/ stay out of the release_90 denominator (they are CI /
governance / audit code, not the shipped product), but they must be measured by
a DEDICATED profile so a regression in a gate, verifier, or auditor is
observable. This binds that profile to structural contracts: it exists, it
sources both tools and scripts, it does not smuggle any of its own source into
`omit`, and it is routed through the component matrix.
"""

from __future__ import annotations

import configparser
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "configs" / "quality" / "governance_tools.coveragerc"
MATRIX = ROOT / "data" / "testing" / "component_test_matrix.json"


def _source_roots() -> set[str]:
    parser = configparser.ConfigParser()
    parser.read(PROFILE, encoding="utf-8")
    raw = parser.get("run", "source")
    return {line.strip() for line in raw.splitlines() if line.strip()}


def _omit_patterns() -> list[str]:
    parser = configparser.ConfigParser()
    parser.read(PROFILE, encoding="utf-8")
    if not parser.has_option("report", "omit"):
        return []
    raw = parser.get("report", "omit")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def test_profile_exists_and_parses() -> None:
    assert PROFILE.is_file(), f"missing governance-tooling profile {PROFILE}"
    _source_roots()  # must parse [run] source


def test_source_includes_tools_and_scripts() -> None:
    roots = _source_roots()
    assert "tools" in roots, f"governance profile must source 'tools', got {roots}"
    assert "scripts" in roots, f"governance profile must source 'scripts', got {roots}"


def test_omit_does_not_hide_its_own_source() -> None:
    """A lower honest number beats a higher lying one: no concrete omit path may
    be a child of a source root (glob/cross-cutting patterns are exempt)."""
    roots = _source_roots()
    for pattern in _omit_patterns():
        if any(ch in pattern for ch in "*?["):
            continue  # e.g. tests/**, **/__init__.py — cross-cutting, not source-hiding
        first = Path(pattern).parts[0] if pattern else ""
        assert first not in roots, (
            f"omit {pattern!r} hides a child of source root {first!r} — remove it "
            f"from source instead of smuggling it into omit."
        )


def test_source_roots_are_real_directories() -> None:
    for root in _source_roots():
        assert (ROOT / root).is_dir(), f"governance profile sources non-existent root {root!r}"


def test_profile_measures_the_audit_and_verifier_tooling() -> None:
    """The evidence tooling this profile exists to protect is under its source."""
    roots = _source_roots()
    for verifier in (
        "tools/audit_coverage_surface.py",
        "tools/rvg_audit.py",
        "tools/rvg_verify_artifacts.py",
    ):
        assert (ROOT / verifier).is_file(), f"expected verifier {verifier} to exist"
        assert Path(verifier).parts[0] in roots, (
            f"{verifier} is not under any governance-profile source root {roots}"
        )


def test_matrix_routes_the_governance_tooling_profile() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    components = matrix.get("components", [])
    this_test = "tests/tools/test_governance_tooling_coverage_profile.py"
    routed = any(
        this_test in comp.get("selectors", [])
        or "configs/quality/governance_tools.coveragerc" in comp.get("patterns", [])
        for comp in components
    )
    assert routed, (
        "governance_tools.coveragerc / its test are not routed by any component in "
        "data/testing/component_test_matrix.json"
    )
