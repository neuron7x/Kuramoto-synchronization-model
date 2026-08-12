# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsification suite for the config-reference gate.

The gate's whole claim is that a config which NAMES a module or a path is making
an existence claim, and that the claim is now checked. These tests attack that:
each one plants a reference the gate must reject. A gate that cannot go RED is
not a gate, so the positive controls below are the point of the file -- the
"repo is clean" test alone would pass just as happily if the checker were a stub
that always returned 0.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "ci" / "check_config_references.py"


def _load_gate(root: Path):
    """Load the checker with REPO_ROOT rebound to a scratch tree."""
    spec = importlib.util.spec_from_file_location("_cfgref", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_cfgref"] = mod
    spec.loader.exec_module(mod)
    mod.REPO_ROOT = root
    return mod


def _tree(root: Path) -> None:
    """A minimal repo: one real module, one real package path."""
    pkg = root / "geosync" / "core" / "strategies"
    pkg.mkdir(parents=True)
    for parent in (root / "geosync", root / "geosync" / "core", pkg):
        (parent / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "signals.py").write_text("def moving_average_signal(x):\n    return x\n", encoding="utf-8")
    gov = root / "geosync" / "application" / "governance"
    gov.mkdir(parents=True)
    (gov / "claim_ledger.py").write_text("LEDGER = 1\n", encoding="utf-8")
    (root / "configs" / "templates").mkdir(parents=True)
    (root / ".claude" / "commit_acceptors").mkdir(parents=True)


def _run(root: Path) -> list[str]:
    gate = _load_gate(root)
    violations: list[str] = []
    for pattern in gate.SCAN_GLOBS:
        for f in sorted(root.glob(pattern)):
            if f.is_file():
                violations.extend(gate._scan_file(f))
    return violations


def test_repo_is_clean() -> None:
    """The live tree must hold: every named module and path resolves in-repo."""
    proc = subprocess.run(
        [sys.executable, str(GATE)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_frozen_exemption_matches_the_sha256_contract() -> None:
    """The gate's one exemption must equal the set the non-mutation contract pins.

    The gate skips the D-002G artefacts because their bytes are locked by sha256 and a
    pre-registration record must not be rewritten to match a later layout. That is a
    real exemption, and an exemption nobody checks is a hole: if a file were quietly
    added here, the gate would stop looking at it while nothing else forced it to stay
    frozen. So the two sets are pinned to each other — drift in either direction fails.
    """
    import re

    gate = _load_gate(REPO_ROOT)
    locked = set(
        re.findall(
            r'"([^"]+\.(?:yaml|md|json))"',
            (REPO_ROOT / "tests/systemic_risk/test_d002g_m2_locked_governance_untouched.py")
            .read_text(encoding="utf-8"),
        )
    )
    assert gate._FROZEN_ARTEFACTS == frozenset(locked), (
        "the gate's frozen-exemption set drifted from the sha256 non-mutation contract; "
        f"only in gate: {sorted(gate._FROZEN_ARTEFACTS - locked)}; "
        f"only in contract: {sorted(locked - gate._FROZEN_ARTEFACTS)}"
    )


def test_r1_entrypoint_that_leaves_the_repository_is_caught(tmp_path: Path) -> None:
    """POSITIVE CONTROL: the exact defect that executed another project's code.

    `core.strategies.signals` does not exist here. importlib would not fail on
    it -- it would search sys.path and import whatever else answers to `core`.
    The gate must reject it precisely because Python would NOT.
    """
    _tree(tmp_path)
    (tmp_path / "configs" / "templates" / "backtest.yaml.j2").write_text(
        "strategy:\n  entrypoint: core.strategies.signals:moving_average_signal\n",
        encoding="utf-8",
    )
    violations = _run(tmp_path)
    assert violations, "gate stayed GREEN on an entrypoint that resolves outside the repo"
    assert any("R1" in v and "core.strategies.signals" in v for v in violations)


def test_r1_entrypoint_resolving_in_repo_passes(tmp_path: Path) -> None:
    """NEGATIVE CONTROL: the canonical entrypoint must not be flagged."""
    _tree(tmp_path)
    (tmp_path / "configs" / "templates" / "backtest.yaml.j2").write_text(
        "strategy:\n  entrypoint: geosync.core.strategies.signals:moving_average_signal\n",
        encoding="utf-8",
    )
    assert _run(tmp_path) == []


def test_r1_module_exists_but_callable_does_not(tmp_path: Path) -> None:
    """A module that resolves but lacks the callable is still a broken claim."""
    _tree(tmp_path)
    (tmp_path / "configs" / "templates" / "backtest.yaml.j2").write_text(
        "strategy:\n  entrypoint: geosync.core.strategies.signals:no_such_function\n",
        encoding="utf-8",
    )
    violations = _run(tmp_path)
    assert any("R1" in v and "no_such_function" in v for v in violations)


def test_r3_prohibition_whose_target_moved_is_a_disarmed_fence(tmp_path: Path) -> None:
    """POSITIVE CONTROL: the d002g defect.

    The acceptor forbids `application/governance/claim_ledger.py`. That file is
    now `geosync/application/governance/claim_ledger.py`. The fence names a path
    that cannot appear in any diff, so it protects nothing -- silently.
    """
    _tree(tmp_path)
    (tmp_path / ".claude" / "commit_acceptors" / "demo.yaml").write_text(
        'status: ACTIVE\ndiff_scope:\n  forbidden_paths:\n'
        '    - "application/governance/claim_ledger.py"\n',
        encoding="utf-8",
    )
    violations = _run(tmp_path)
    assert any("R3" in v and "disarmed fence" in v for v in violations)


def test_r3_does_not_fire_on_a_prohibition_with_no_twin(tmp_path: Path) -> None:
    """A prohibition MAY name a path that must never exist -- that is its job.

    Only a target that MOVED (the twin exists under geosync/) is a defect. This
    is what keeps the twin rule free of false positives on preventive fences.
    """
    _tree(tmp_path)
    (tmp_path / ".claude" / "commit_acceptors" / "demo.yaml").write_text(
        'status: ACTIVE\ndiff_scope:\n  forbidden_paths:\n'
        '    - "never/created/secret_backdoor.py"\n',
        encoding="utf-8",
    )
    assert _run(tmp_path) == []


def test_r2_declared_root_that_does_not_exist_is_caught(tmp_path: Path) -> None:
    """A contract keyed on a root that is not there enforces nothing."""
    _tree(tmp_path)
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "docs" / "architecture" / "connectome.yaml").write_text(
        'scan_roots:\n  - "geosync"\n  - "src/geosync"\n',
        encoding="utf-8",
    )
    violations = _run(tmp_path)
    assert any("R2" in v and "src/geosync" in v for v in violations)


@pytest.mark.parametrize("root_value", ["geosync/core/strategies", "geosync/core/strategies/signals"])
def test_r2_accepts_both_a_package_and_a_module(tmp_path: Path, root_value: str) -> None:
    """A declared root may name a directory OR a module file (import_roots does both)."""
    _tree(tmp_path)
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "docs" / "architecture" / "connectome.yaml").write_text(
        f'domains:\n  d:\n    import_roots:\n      - "{root_value}"\n',
        encoding="utf-8",
    )
    assert _run(tmp_path) == []
