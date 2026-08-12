# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration tests for the deterministic ActionResultComparator.

These tests exercise the comparator through real package boundaries:
    1. fail-closed contract on a missing expected model
       (no post-factum default Prediction fabrication)
    2. full lifecycle ordering with sanctioned match
    3. ledger validator subprocess
    4. import-time module isolation (no forbidden runtime modules)
    5. AST inspection of the comparator source
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from geosync_hpc.control import (
    ActionResultStatus,
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
)

REPO_ROOT: Path = Path(__file__).resolve().parents[3]
COMPARATOR_SRC: Path = REPO_ROOT / "geosync_hpc" / "control" / "action_result_comparator.py"


def test_strict_comparator_rejects_missing_expected_model() -> None:
    """The strict comparator fails closed on a missing expected model.

    A missing expected model is a hard contract violation: the witness
    reports ``INVALID_INPUT`` and requests rollback instead of fabricating
    a default prediction.
    """

    observed = ObservedActionResult(
        action_id="any",
        observed_seq=10,
        observed_result=(1.0, 0.0),
    )
    witness = accept_action_result(None, observed)
    assert witness.status is ActionResultStatus.INVALID_INPUT
    assert witness.accepted is False
    assert witness.rollback_required is True
    assert witness.reason.startswith("INVALID_EXPECTED_MODEL")


def test_lifecycle_seq_ordering_sanctions_exact_match() -> None:
    """Full sequence ordering ``1 < 2 < 3`` plus exact match -> SANCTIONED."""

    expected = ExpectedResultModel(
        action_id="lifecycle-1",
        action_type="trade",
        expected_result=(1.0, 0.0, -1.0),
        expected_result_variance=None,
        context_signature=(0.5,),
        model_created_seq=1,
        action_started_seq=2,
        error_threshold=0.5,
        rollback_threshold=1.0,
    )
    observed = ObservedActionResult(
        action_id="lifecycle-1",
        observed_seq=3,
        observed_result=(1.0, 0.0, -1.0),
    )
    witness = accept_action_result(expected, observed)
    assert witness.status is ActionResultStatus.SANCTIONED_MATCH
    assert witness.accepted is True
    assert witness.dissolved is True


def test_ledger_validator_accepts_new_entry() -> None:
    """Run the ledger validator as a subprocess; expect exit 0."""

    result = subprocess.run(  # noqa: S603 — fixed argv, no shell.
        [sys.executable, "-m", "tools.archive.validate_action_result_acceptor"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


_FORBIDDEN_RUNTIME_PREFIXES: tuple[str, ...] = (
    "geosync_hpc.trading",
    "geosync_hpc.execution",
    "geosync_hpc.forecast",
    "geosync_hpc.policy",
)
_FORBIDDEN_RUNTIME_EXACT: frozenset[str] = frozenset(
    {
        "nak_controller.aar.memory",
    }
)


def test_import_boundary_no_forbidden_modules() -> None:
    """Importing the comparator must not pull in trading / policy modules.

    The test runner's ``sys.modules`` is polluted by other tests in the same
    session, so we cannot inspect it in-process — that produced false failures
    in CI when unrelated tests had already imported ``geosync_hpc.policy``.
    Instead we spawn a fresh subprocess that imports ONLY the comparator and
    reports its own ``sys.modules`` snapshot. That snapshot is the only honest
    evidence of what the comparator's import graph drags in.
    """
    probe = (
        "import sys\n"
        "import geosync_hpc.control.action_result_comparator  # noqa: F401\n"
        "print('|'.join(sorted(sys.modules.keys())))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = set(result.stdout.strip().split("|"))
    for name in loaded:
        if name in _FORBIDDEN_RUNTIME_EXACT:
            pytest.fail(f"forbidden module imported via comparator path: {name}")
        for prefix in _FORBIDDEN_RUNTIME_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                pytest.fail(f"forbidden module imported via comparator path: {name}")


_ALLOWED_TOP_LEVEL_IMPORTS: frozenset[str] = frozenset(
    {
        "math",
        "hashlib",
        "json",
        "enum",
        "dataclasses",
        "typing",
        "collections",  # for "collections.abc"
        "__future__",
    }
)


def _import_root(module_name: str) -> str:
    return module_name.split(".", 1)[0]


def test_module_importable_in_isolation() -> None:
    """AST: the comparator may import only stdlib modules — no geosync_hpc.*."""

    source = COMPARATOR_SRC.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(COMPARATOR_SRC))

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.append(node.module)

    for module_name in imports:
        root = _import_root(module_name)
        msg_root = (
            f"comparator imports disallowed module {module_name!r}; "
            f"only stdlib modules from {sorted(_ALLOWED_TOP_LEVEL_IMPORTS)} are permitted"
        )
        assert root in _ALLOWED_TOP_LEVEL_IMPORTS, msg_root
        msg_geosync = f"comparator must not import geosync_hpc.* (found: {module_name})"
        assert not module_name.startswith("geosync_hpc"), msg_geosync
