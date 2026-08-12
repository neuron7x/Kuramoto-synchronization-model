# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression guard: dependency-audit Make targets must fail closed.

DEBT_3 (dependency security-gate debt): the ``audit`` and ``deps-audit``
targets previously masked vulnerabilities with ``|| true`` / ``|| echo``,
so ``make`` reported success while pip-audit had found issues. This test
makes that defect class *structurally detectable* — it fails if any
audit recipe reintroduces soft-fail masking, or stops routing through the
fail-closed ``scripts/dependency_audit.py`` driver.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_MAKEFILE = Path("Makefile")

# Targets whose recipes audit dependency vulnerabilities and MUST fail closed.
_FAIL_CLOSED_TARGETS: tuple[str, ...] = ("audit", "deps-audit")

# Soft-fail masking idioms that convert a non-zero audit into a green build.
_SOFT_FAIL_PATTERNS: tuple[str, ...] = ("|| true", "|| :", "|| echo")

# The canonical fail-closed driver (returns non-zero on any finding).
_FAIL_CLOSED_DRIVER = "scripts/dependency_audit.py"


@pytest.fixture(scope="module")
def makefile_text() -> str:
    if not _MAKEFILE.exists():
        pytest.skip("Makefile not present in CWD")
    return _MAKEFILE.read_text(encoding="utf-8")


def _recipe_lines(makefile_text: str, target: str) -> list[str]:
    """Return the recipe lines (tab-indented body) of a Make ``target``."""
    lines = makefile_text.splitlines()
    header = re.compile(rf"^{re.escape(target)}:")
    body: list[str] = []
    capturing = False
    for line in lines:
        if header.match(line):
            capturing = True
            continue
        if capturing:
            # Recipe lines are tab-indented; the first non-tab line ends it.
            if line.startswith("\t"):
                body.append(line)
            elif line.strip() == "":
                continue
            else:
                break
    return body


@pytest.mark.parametrize("target", _FAIL_CLOSED_TARGETS)
def test_audit_target_has_no_soft_fail_masking(makefile_text: str, target: str) -> None:
    body = _recipe_lines(makefile_text, target)
    assert body, f"target '{target}:' not found or has an empty recipe"
    joined = "\n".join(body)
    offenders = [pat for pat in _SOFT_FAIL_PATTERNS if pat in joined]
    assert not offenders, (
        f"target '{target}' reintroduced soft-fail masking {offenders}; "
        f"dependency audits must fail closed.\nRecipe:\n{joined}"
    )


@pytest.mark.parametrize("target", _FAIL_CLOSED_TARGETS)
def test_audit_target_routes_through_fail_closed_driver(
    makefile_text: str, target: str
) -> None:
    body = "\n".join(_recipe_lines(makefile_text, target))
    assert _FAIL_CLOSED_DRIVER in body, (
        f"target '{target}' must invoke {_FAIL_CLOSED_DRIVER} (which exits "
        f"non-zero on findings) rather than a bare, maskable pip-audit call"
    )


def test_no_masked_pip_audit_anywhere_in_makefile(makefile_text: str) -> None:
    """No pip-audit invocation anywhere may be neutralised by ``|| true``/``|| echo``."""
    masked: list[str] = []
    for line in makefile_text.splitlines():
        invokes_audit = "pip_audit" in line or "python -m pip-audit" in line
        if invokes_audit and any(pat in line for pat in _SOFT_FAIL_PATTERNS):
            masked.append(line.strip())
    assert not masked, "masked pip-audit invocation(s) found:\n" + "\n".join(masked)


def test_fail_closed_driver_exists() -> None:
    assert Path(_FAIL_CLOSED_DRIVER).is_file(), (
        f"{_FAIL_CLOSED_DRIVER} missing — the audit targets depend on it"
    )
