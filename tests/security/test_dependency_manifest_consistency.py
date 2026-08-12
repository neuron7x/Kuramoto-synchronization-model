# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the security-floor manifest-consistency gate.

Proves the gate (a) catches a manifest floor below the security policy and
(b) confirms pyproject.toml — the ``pip install .`` source of truth — is
consistent with constraints/security.txt on the live tree.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from packaging.version import Version

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_dependency_manifest_consistency",
    _ROOT / "tools/security/check_dependency_manifest_consistency.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
# Register before exec so the frozen-dataclass __module__ resolution succeeds.
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)


def test_security_critical_set_covers_named_cve_packages() -> None:
    for pkg in ("pyjwt", "cryptography", "aiohttp", "starlette", "tornado", "fastapi"):
        assert pkg in _mod.SECURITY_CRITICAL


def test_normalize_drops_extras_and_case() -> None:
    assert _mod._normalize("PyJWT[crypto]") == "pyjwt"
    assert _mod._normalize("python_multipart") == "python-multipart"


def test_checker_flags_floor_below_policy() -> None:
    policy = {"pyjwt": Version("2.13.0")}
    violations = _mod.check_manifest("fake.toml", {"pyjwt": Version("2.12.0")}, policy)
    assert len(violations) == 1
    assert violations[0].package == "pyjwt"
    assert violations[0].declared_floor == "2.12.0"
    assert violations[0].required_floor == "2.13.0"


def test_checker_passes_floor_at_or_above_policy() -> None:
    policy = {"cryptography": Version("49.0.0")}
    assert _mod.check_manifest("fake.toml", {"cryptography": Version("49.0.0")}, policy) == []
    assert _mod.check_manifest("fake.toml", {"cryptography": Version("50.0.0")}, policy) == []


def test_pyproject_security_floors_consistent_with_policy() -> None:
    """Live invariant: pyproject.toml admits no security-critical version below
    the constraints/security.txt floor. This is the enforceable source of truth
    for ``pip install .``."""
    strict, _advisory = _mod.evaluate()
    assert strict == [], "pyproject.toml security floors lag constraints/security.txt: " + ", ".join(
        str(v) for v in strict
    )


def test_all_manifests_consistent_with_security_floor() -> None:
    """Live all-strict invariant (P0-1): no manifest — pyproject.toml,
    requirements.txt, or requirements-backend.txt — admits a security-critical
    version below the constraints/security.txt floor. The advisory carve-out for
    requirements*.txt (PR #1111 ownership) is closed, so every install path is
    floor-consistent."""
    strict, advisory = _mod.evaluate()
    offenders = strict + advisory
    assert offenders == [], "manifest security floors lag constraints/security.txt: " + ", ".join(
        str(v) for v in offenders
    )


def test_main_is_strict_by_default() -> None:
    """The default CLI invocation enforces every manifest (exit 0 only when all
    manifests are floor-consistent), with no flag required."""
    assert _mod.main([]) == 0


def test_advisory_requirements_flag_downgrades_requirements() -> None:
    """The deprecated --advisory-requirements escape hatch still parses and, on a
    floor-consistent tree, also passes — proving the flag is a reporting-mode
    toggle, not a correctness bypass."""
    assert _mod.main(["--advisory-requirements"]) == 0
