# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression guard for inline-comment handling in dependency drift parsing.

A pinned manifest may carry a pip-style inline comment after a requirement
(e.g. ``PyJWT[crypto]>=2.13.0  # GHSA-... vulnerable below``). Both dependency
drift checkers must parse such lines, not crash on them — a parse crash would
abort the run before any lock/constraint drift could be reported, silently
weakening the dependency gate's stale-drift leg.

The repository's own ``requirements.txt`` carries exactly such a line, so this
is the load-bearing guard that ``dependency-health`` and
``check_dependency_drift`` stay runnable on the shipping manifests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts.dependency_health import (
    _strip_inline_comment,
    build_marker_environment,
    load_locked_dependencies,
    load_requirement_specs,
)

ROOT = Path(__file__).resolve().parents[2]
DRIFT_SCRIPT = ROOT / "scripts" / "security" / "check_dependency_drift.py"


def _load_drift() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_dependency_drift", DRIFT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_dependency_drift"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("PyJWT[crypto]>=2.13.0  # GHSA-xgmm; <2.13.0 vulnerable", "PyJWT[crypto]>=2.13.0"),
        ("requests==2.32.3   # pinned for CVE fix", "requests==2.32.3"),
        ("numpy==2.1.0", "numpy==2.1.0"),
        ("flask>=3.0\t# tab-separated comment", "flask>=3.0"),
        # A '#' NOT preceded by whitespace is part of the token, not a comment.
        ("pkg==1.0#notacomment", "pkg==1.0#notacomment"),
    ],
)
def test_strip_inline_comment(line: str, expected: str) -> None:
    assert _strip_inline_comment(line) == expected


def test_health_load_requirement_specs_parses_inline_comment(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text(
        "# full-line comment\n"
        "PyJWT[crypto]>=2.13.0          # GHSA-xgmm-8j9v-c9wx; <2.13.0 vulnerable\n"
        "requests==2.32.3\n",
        encoding="utf-8",
    )
    specs = load_requirement_specs([req], environment=build_marker_environment("3.12"))
    assert {spec.canonical_name for spec in specs} == {"pyjwt", "requests"}


def test_health_load_locked_dependencies_parses_inline_comment(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "pyjwt==2.13.0    # transitively pinned\nrequests==2.32.3\n",
        encoding="utf-8",
    )
    locked = load_locked_dependencies(lock)
    assert set(locked) == {"pyjwt", "requests"}
    assert locked["pyjwt"][0].version == "2.13.0"


def test_drift_checker_parses_inline_comment(tmp_path: Path) -> None:
    drift = _load_drift()
    req = tmp_path / "requirements.txt"
    req.write_text(
        "PyJWT[crypto]>=2.13.0          # GHSA-xgmm-8j9v-c9wx; <2.13.0 vulnerable\n"
        "requests==2.32.3\n",
        encoding="utf-8",
    )
    parsed = drift._parse_requirements_file(req)
    assert {_normalize_name(r.name) for r in parsed} == {"pyjwt", "requests"}


def test_drift_lock_parse_strips_inline_comment(tmp_path: Path) -> None:
    drift = _load_drift()
    lock = tmp_path / "requirements.lock"
    lock.write_text("tornado==6.5.7  # security floor\n", encoding="utf-8")
    locked = drift._parse_lock(lock)
    # Version must be the clean pin, not "6.5.7  # security floor".
    assert locked["tornado"] == "6.5.7"


def _normalize_name(name: str) -> str:
    return name.lower().replace("_", "-")
