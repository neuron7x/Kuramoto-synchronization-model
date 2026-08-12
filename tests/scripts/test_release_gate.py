# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Release-gate harness — behavioural tests.

The gate's own promise is falsifiable: it must (1) return only valid
statuses, (2) make the overall verdict RED whenever any gating probe is
RED or MANUAL, (3) cold-verify MANIFEST hashes by content (a one-byte
edit flips a GREEN to RED), and (4) classify first-party `src.*` imports
as a violation.
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
SCRIPT_PATH = ROOT / "scripts" / "ci" / "release_gate.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("release_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_gate"] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path, files: dict[str, str]) -> None:
    """Create a committed git repo with the given files, then write a MANIFEST
    that covers every tracked in-scope file (the canonical clean state)."""
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    # Build the manifest exactly as generate_manifest would for this tree.
    lines = sorted(
        f"{hashlib.sha256((repo / rel).read_bytes()).hexdigest()}  ./{rel}"
        for rel in files
    )
    (repo / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _git(repo, "add", "MANIFEST.sha256")
    _git(repo, "commit", "-q", "-m", "manifest")


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load()


def test_all_probes_return_valid_status(mod: Any) -> None:
    valid = {mod.GREEN, mod.RED, mod.MANUAL}
    for r in mod.evaluate(False):
        assert r.status in valid, f"{r.pid} returned {r.status}"
        assert r.evidence, f"{r.pid} has empty evidence"


def test_red_or_manual_forces_red_verdict(mod: Any) -> None:
    rc = mod.main(["--json", "/dev/null"])
    # On the live tree at least one gating probe is RED/MANUAL, so the gate
    # must exit nonzero. (If the repo ever reaches all-GREEN this asserts the
    # inverse contract and should be updated deliberately.)
    assert rc == 1


def test_manifest_coldverify_clean_tree_green(mod: Any, tmp_path: Path) -> None:
    """Non-vacuous positive: an intact repo whose manifest covers the tree
    must read GREEN (so the RED cases below prove detection, not a stuck RED)."""
    _init_repo(tmp_path, {"a.py": "print(1)\n", "pkg/b.txt": "hello\n"})
    orig_root = mod.ROOT
    try:
        mod.ROOT = tmp_path
        status, ev = mod.probe_d_manifest_coldverify(False)
        assert status == mod.GREEN, ev
    finally:
        mod.ROOT = orig_root


def test_manifest_coldverify_detects_tamper(mod: Any, tmp_path: Path) -> None:
    """A one-byte edit to a *still-listed* file flips GREEN → RED (mismatch)."""
    _init_repo(tmp_path, {"a.py": "print(1)\n", "pkg/b.txt": "hello\n"})
    orig_root = mod.ROOT
    try:
        mod.ROOT = tmp_path
        assert mod.probe_d_manifest_coldverify(False)[0] == mod.GREEN
        (tmp_path / "a.py").write_text("print(2)\n", encoding="utf-8")
        status, ev = mod.probe_d_manifest_coldverify(False)
        assert status == mod.RED
        assert "mismatch" in ev
    finally:
        mod.ROOT = orig_root


def test_manifest_coldverify_M5_dropped_line_and_corrupt(mod: Any, tmp_path: Path) -> None:
    """DS-09 / M5: drop a file's line from MANIFEST AND corrupt that same file.

    The old coverage-blind probe iterated only listed lines, so a dropped line
    silently removed verification → false GREEN. The canonical set-comparison
    now flags the file as *uncovered* → RED."""
    _init_repo(tmp_path, {"a.py": "print(1)\n", "pkg/b.txt": "hello\n"})
    manifest = tmp_path / "MANIFEST.sha256"
    kept = [ln for ln in manifest.read_text().splitlines() if "a.py" not in ln]
    manifest.write_text("\n".join(kept) + "\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("MALICIOUS\n", encoding="utf-8")  # corrupt the unlisted file
    orig_root = mod.ROOT
    try:
        mod.ROOT = tmp_path
        status, ev = mod.probe_d_manifest_coldverify(False)
        assert status == mod.RED, ev
        assert "uncovered" in ev
    finally:
        mod.ROOT = orig_root


def test_manifest_coldverify_M6_untracked_by_manifest(mod: Any, tmp_path: Path) -> None:
    """DS-09 / M6: add a git-tracked file that is absent from the manifest.

    The manifest must COVER the tree; an unlisted tracked file is RED."""
    _init_repo(tmp_path, {"a.py": "print(1)\n"})
    rogue = tmp_path / "rogue.py"
    rogue.write_text("import os\n", encoding="utf-8")
    _git(tmp_path, "add", "rogue.py")
    _git(tmp_path, "commit", "-q", "-m", "add rogue")
    orig_root = mod.ROOT
    try:
        mod.ROOT = tmp_path
        status, ev = mod.probe_d_manifest_coldverify(False)
        assert status == mod.RED, ev
        assert "uncovered" in ev
    finally:
        mod.ROOT = orig_root


def test_src_import_regex_matches_first_party(mod: Any) -> None:
    assert mod._SRC_IMPORT_RE.search("from src.core import X")
    assert mod._SRC_IMPORT_RE.search("import src")
    assert not mod._SRC_IMPORT_RE.search("from geosync.core import X")
    assert not mod._SRC_IMPORT_RE.search("from mysrc import X")


def test_path_hack_regex(mod: Any) -> None:
    assert mod._PATH_HACK_RE.search("sys.path.insert(0, '..')")
    assert mod._PATH_HACK_RE.search("sys.path.append(x)")
    assert not mod._PATH_HACK_RE.search("path = sys.path")
