# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsification battery for the canonical-counts reconciliation probe.

The probe exists to kill one failure class: headline numbers quoted from
memory, each true at a different commit, none traceable. These tests pin that
each count comes from its gate's own source and that --verify actually fails
on drift (a verifier that cannot fail is not a verifier).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "canonical_counts.py"
_spec = importlib.util.spec_from_file_location("canonical_counts", _MOD_PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def test_build_produces_all_four_counts_with_sources() -> None:
    payload = _mod.build()
    counts = payload["counts"]
    assert set(counts) == {
        "test_files_tracked",
        "manifest_entries",
        "invariants",
        "claim_surfaces",
    }
    for entry in counts.values():
        assert isinstance(entry["value"], int) and entry["value"] > 0
        assert entry["source"]
    assert len(payload["git_sha"]) == 40


def test_test_file_count_matches_release_gate_rule() -> None:
    # the probe must use the SAME rule as release_gate probe P.tests
    tracked = _mod._tracked_files()
    expected = sum(1 for rel in tracked if "/test_" in f"/{rel}" and rel.endswith(".py"))
    assert _mod.count_test_files() == expected


def test_verify_fails_on_drift(tmp_path, monkeypatch) -> None:
    # positive control: a verifier that cannot fail is not a verifier
    stale = _mod.build()
    stale["counts"]["invariants"]["value"] += 1
    artifact = tmp_path / "canonical_counts.json"
    artifact.write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setattr(_mod, "ARTIFACT", artifact)
    assert _mod.main(["--verify"]) == 1


def test_verify_passes_on_fresh_artifact(tmp_path, monkeypatch) -> None:
    artifact = tmp_path / "canonical_counts.json"
    monkeypatch.setattr(_mod, "ARTIFACT", artifact)
    assert _mod.main([]) == 0
    assert _mod.main(["--verify"]) == 0


def test_verify_fails_when_artifact_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_mod, "ARTIFACT", tmp_path / "missing.json")
    assert _mod.main(["--verify"]) == 1
