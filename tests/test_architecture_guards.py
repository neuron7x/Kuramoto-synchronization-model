# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

from scripts.check_config_single_source import check_config_single_source
from scripts.check_namespace_integrity import check_namespace_integrity
from scripts.check_single_entrypoint import check_single_entrypoint

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_namespace_integrity_has_no_violations() -> None:
    assert check_namespace_integrity(REPO_ROOT) == []


def test_namespace_integrity_ignores_hidden_dirs(tmp_path: Path) -> None:
    """A canonical marker inside a hidden dir (e.g. an agent worktree under
    ``.claude/worktrees``) must NOT be reported as a violation.

    Regression: the broad scan used to rglob the whole tree and flag
    ``.claude/worktrees/agent-*/src/geosync/...`` — false positives that fire on
    any developer machine with worktrees yet are invisible on CI's clean
    checkout, so the bug could never surface where it is enforced.
    """
    canonical_root = tmp_path / "src" / "geosync"
    canonical_root.mkdir(parents=True)
    (canonical_root / "__init__.py").write_text("__CANONICAL__ = True\n", encoding="utf-8")

    # A hidden worktree that carries its OWN canonical-marked tree.
    rogue = tmp_path / ".claude" / "worktrees" / "agent-deadbeef" / "src" / "geosync" / "data"
    rogue.mkdir(parents=True)
    (rogue / "__init__.py").write_text("__CANONICAL__ = True\n", encoding="utf-8")

    assert check_namespace_integrity(tmp_path) == []


def test_namespace_integrity_still_flags_visible_rogue_canonical(tmp_path: Path) -> None:
    """The hidden-dir exemption must not weaken the real guard: a canonical
    marker in a NON-hidden, non-``src/geosync`` package is still a violation."""
    canonical_root = tmp_path / "src" / "geosync"
    canonical_root.mkdir(parents=True)
    (canonical_root / "__init__.py").write_text("__CANONICAL__ = True\n", encoding="utf-8")

    rogue_pkg = tmp_path / "analytics" / "rogue"
    rogue_pkg.mkdir(parents=True)
    (rogue_pkg / "__init__.py").write_text("__CANONICAL__ = True\n", encoding="utf-8")

    violations = check_namespace_integrity(tmp_path)
    assert [v.path for v in violations] == [Path("analytics/rogue/__init__.py")]


@pytest.mark.parametrize("hidden", [".git", ".venv", ".tox", ".mypy_cache"])
def test_namespace_integrity_skips_known_hidden_trees(tmp_path: Path, hidden: str) -> None:
    canonical_root = tmp_path / "src" / "geosync"
    canonical_root.mkdir(parents=True)
    (canonical_root / "__init__.py").write_text("__CANONICAL__ = True\n", encoding="utf-8")

    vendored = tmp_path / hidden / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "__init__.py").write_text("__CANONICAL__ = True\n", encoding="utf-8")

    assert check_namespace_integrity(tmp_path) == []


def test_single_entrypoint_guard_has_no_violations() -> None:
    assert check_single_entrypoint(REPO_ROOT) == []


def test_config_single_source_guard_has_no_violations() -> None:
    assert check_config_single_source(REPO_ROOT) == []
