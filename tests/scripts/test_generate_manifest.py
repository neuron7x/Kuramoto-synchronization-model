# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""generate_manifest — cold-verify parity (DS-09) + dirty-tree guard (DS-23).

The manifest is the supply-chain integrity proof. Two falsifiable promises:

* ``cold_verify`` is a symmetric set comparison (manifest file-set == in-scope
  git-tracked file-set, plus per-file hash) — dropping or omitting a line is
  detected, not silently ignored (this is the SAME function the release gate's
  D.manifest probe delegates to, so the two surfaces cannot diverge).
* ``write`` (regenerate) REFUSES on a dirty tree, because it hashes working-tree
  bytes for a file-set taken from the index — regenerating dirty would certify
  content diverging from HEAD (a partial commit reads GREEN locally, RED on a
  fresh clone).
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "generate_manifest.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("generate_manifest_uut", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path, files: dict[str, str]) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


# --------------------------------------------------------------------------
# DS-09 — cold_verify is authoritative (set comparison, not listed-only)
# --------------------------------------------------------------------------
def test_cold_verify_clean_positive(mod: Any, tmp_path: Path) -> None:
    _init_repo(tmp_path, {"a.py": "x=1\n", "d/b.txt": "hi\n"})
    assert mod.write(tmp_path) == 0
    ok, msg = mod.cold_verify(tmp_path)
    assert ok, msg
    assert mod.check(tmp_path) == 0  # CLI parity (drives check_root_manifest.py)


def test_cold_verify_dropped_line_is_red(mod: Any, tmp_path: Path) -> None:
    _init_repo(tmp_path, {"a.py": "x=1\n", "d/b.txt": "hi\n"})
    assert mod.write(tmp_path) == 0
    manifest = tmp_path / "MANIFEST.sha256"
    kept = [ln for ln in manifest.read_text().splitlines() if "a.py" not in ln]
    manifest.write_text("\n".join(kept) + "\n", encoding="utf-8")
    ok, msg = mod.cold_verify(tmp_path)
    assert not ok and "uncovered" in msg, msg


# --------------------------------------------------------------------------
# DS-23 — dirty-tree regenerate guard
# --------------------------------------------------------------------------
def test_write_refuses_on_dirty_tree(mod: Any, tmp_path: Path) -> None:
    _init_repo(tmp_path, {"a.py": "x=1\n"})
    assert mod.write(tmp_path) == 0  # clean tree regenerates fine
    (tmp_path / "a.py").write_text("x=999  # uncommitted\n", encoding="utf-8")
    rc = mod.write(tmp_path)  # dirty working tree
    assert rc == 2, "regenerate must refuse (nonzero) on a dirty tree"
    assert mod.write(tmp_path, allow_dirty=True) == 0  # explicit override still works


def test_write_refuses_on_staged_uncommitted_new_file(mod: Any, tmp_path: Path) -> None:
    """Partial-commit trap: a new file staged but not committed must block
    regeneration (else fresh clone lacks it → local GREEN / clone RED)."""
    _init_repo(tmp_path, {"a.py": "x=1\n"})
    (tmp_path / "new.py").write_text("y=2\n", encoding="utf-8")
    _git(tmp_path, "add", "new.py")  # staged, not committed
    assert mod.write(tmp_path) == 2


def test_write_clean_tree_matches_manual_hash(mod: Any, tmp_path: Path) -> None:
    """Non-vacuous: clean-tree regeneration still produces the exact manifest
    (working tree == HEAD passes exactly as before)."""
    _init_repo(tmp_path, {"a.py": "hello\n"})
    assert mod.write(tmp_path) == 0
    want = f"{hashlib.sha256((tmp_path / 'a.py').read_bytes()).hexdigest()}  ./a.py"
    assert (tmp_path / "MANIFEST.sha256").read_text().strip() == want


def test_dirty_guard_ignores_out_of_scope(mod: Any, tmp_path: Path) -> None:
    """A dirty MANIFEST.sha256 itself (out of scope) must NOT block regenerate —
    otherwise the commit-source-then-regenerate workflow is impossible."""
    _init_repo(tmp_path, {"a.py": "x=1\n"})
    assert mod.write(tmp_path) == 0
    _git(tmp_path, "add", "MANIFEST.sha256")
    _git(tmp_path, "commit", "-q", "-m", "manifest")
    # MANIFEST.sha256 now differs from HEAD only if we touch it; touch it:
    (tmp_path / "MANIFEST.sha256").write_text("stale\n", encoding="utf-8")
    assert mod._dirty_in_scope(tmp_path) == []  # out-of-scope diff is ignored
    assert mod.write(tmp_path) == 0  # regenerate proceeds


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
