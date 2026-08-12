# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); MIT
"""REL-002 — prove the two manifest gates have distinct, non-substitutable scopes.

G-ROOT-MANIFEST (check_root_manifest.py) cold-verifies the root MANIFEST.sha256
over every tracked file. G-ARTIFACT-MANIFESTS (check_manifest_hashes.py) only
covers files literally named ``manifest.json``. A PASS of the artifact gate must
not be readable as root-manifest integrity — that was the historical semantic gap
(root manifest drifted 138 commits with no gate red).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(mod_path: str):
    spec = importlib.util.spec_from_file_location("m", ROOT / mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_gates_have_distinct_ids() -> None:
    root_gate = _load("scripts/ci/check_root_manifest.py")
    artifact_gate = _load("scripts/ci/check_manifest_hashes.py")
    assert root_gate.GATE_ID == "G-ROOT-MANIFEST"
    assert artifact_gate.GATE_ID == "G-ARTIFACT-MANIFESTS"
    assert root_gate.GATE_ID != artifact_gate.GATE_ID


def test_artifact_gate_scope_structurally_excludes_root_manifest() -> None:
    # the artifact gate discovers only manifest.json files; it can never open the
    # root MANIFEST.sha256, so its PASS is not evidence of root integrity
    art = _load("scripts/ci/check_manifest_hashes.py")
    discovered = art._discover_manifest_paths()
    assert discovered, "expected at least one manifest.json in the tree"
    assert all(p.name == "manifest.json" for p in discovered)
    assert all(p.name != "MANIFEST.sha256" for p in discovered)


def test_root_gate_passes_on_clean_tree() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/check_root_manifest.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"root gate should pass on clean tree:\n{r.stdout}\n{r.stderr}"
    assert "G-ROOT-MANIFEST" in r.stdout


def test_root_gate_detects_single_byte_drift() -> None:
    # negative control: perturb one tracked file, the root gate must go RED,
    # then restore. Uses a docs file to avoid touching source/tests.
    target = ROOT / "docs" / "RELEASE_GATES.md"
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n<!-- rem-neg-test -->\n")
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts/ci/check_root_manifest.py")],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert r.returncode != 0, "root gate must fail closed on a 1-byte drift"
    finally:
        target.write_bytes(original)
    # confirm restoration leaves the gate green again
    r2 = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/check_root_manifest.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r2.returncode == 0, "gate should be green after restore"
