# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/mutation/falsifier_forge.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tools.mutation.falsifier_forge import forge_candidates


def _good_pattern(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "pattern_id": "P_FAKE",
        "source_ids": ["S99_FAKE"],
        "source_fact_summary": "x",
        "methodological_pattern": "y",
        "geosync_operational_analog": "z",
        "proposed_module": "geosync_hpc/fake/module.py",
        "claim_tier": "ENGINEERING_ANALOG",
        "implementation_status": "IMPLEMENTED",
        "measurable_inputs": ["a"],
        "output_witness": ["b"],
        "null_model": "n",
        "falsifier": "f",
        "deterministic_tests": ["t"],
        "mutation_candidate": "m",
        "ledger_entry_required": True,
    }
    base.update(overrides)
    return base


def _write(path: Path, patterns: list[dict[str, Any]]) -> Path:
    path.write_text(
        yaml.safe_dump({"schema_version": 1, "patterns": patterns}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_forge_emits_candidate_per_known_implemented_pattern(tmp_path: Path) -> None:
    """Every IMPLEMENTED pattern with a matching rule emits a candidate."""
    matrix = _write(
        tmp_path / "trans.yaml",
        [
            _good_pattern(pattern_id="P4_GLOBAL_PARITY_WITNESS"),
            _good_pattern(pattern_id="P5_MOTIONAL_CORRELATION_WITNESS"),
            _good_pattern(pattern_id="P6_COMPOSITE_BINDING_STRUCTURE"),
        ],
    )
    report = forge_candidates(matrix)
    kinds = {c.mutation_kind for c in report.candidates}
    assert "IGNORE_DEPENDENCY_TRUTH" in kinds
    assert "SKIP_SHUFFLED_NULL" in kinds
    assert "TREAT_CORRELATION_AS_BIND" in kinds
    # Cross-cutting evidence-decay rule is ALWAYS emitted.
    assert "MARK_STALE_EVIDENCE_VALID" in kinds


def test_forge_skips_proposed_only_patterns(tmp_path: Path) -> None:
    """PROPOSED status → no candidate (proposing for unbuilt code is a lie)."""
    matrix = _write(
        tmp_path / "trans.yaml",
        [_good_pattern(pattern_id="P4_GLOBAL_PARITY_WITNESS", implementation_status="PROPOSED")],
    )
    report = forge_candidates(matrix)
    pids = {c.pattern_id for c in report.candidates}
    assert "P4_GLOBAL_PARITY_WITNESS" not in pids


def test_forge_skips_unknown_pattern_ids(tmp_path: Path) -> None:
    """Unknown pattern_id → silently skipped (only EVIDENCE_DECAY emits)."""
    matrix = _write(
        tmp_path / "trans.yaml",
        [_good_pattern(pattern_id="P_UNKNOWN")],
    )
    report = forge_candidates(matrix)
    pids = {c.pattern_id for c in report.candidates}
    assert pids == {"EVIDENCE_DECAY"}


def test_forge_dedupes_by_path_and_kind(tmp_path: Path) -> None:
    """Two IMPLEMENTED patterns with same module+kind dedupe to one."""
    matrix = _write(
        tmp_path / "trans.yaml",
        [
            _good_pattern(
                pattern_id="P5_MOTIONAL_CORRELATION_WITNESS",
                proposed_module="x.py",
            ),
            _good_pattern(
                pattern_id="P7_REGIME_FRONT_ROUGHNESS",
                proposed_module="x.py",
            ),
        ],
    )
    report = forge_candidates(matrix)
    skip_null = [c for c in report.candidates if c.mutation_kind == "SKIP_SHUFFLED_NULL"]
    assert len(skip_null) == 1


def test_forge_returns_empty_on_empty_translation(tmp_path: Path) -> None:
    matrix = _write(tmp_path / "trans.yaml", [])
    report = forge_candidates(matrix)
    # Only the cross-cutting evidence-decay candidate remains.
    assert len(report.candidates) == 1
    assert report.candidates[0].mutation_kind == "MARK_STALE_EVIDENCE_VALID"


def test_falsifier_removing_pattern_drops_candidate(tmp_path: Path) -> None:
    """Falsifier: remove P4 from the matrix → IGNORE_DEPENDENCY_TRUTH disappears.

    This is the test the brief calls out as the falsifier surface.
    """
    matrix_with = _write(
        tmp_path / "with.yaml",
        [_good_pattern(pattern_id="P4_GLOBAL_PARITY_WITNESS")],
    )
    matrix_without = _write(tmp_path / "without.yaml", [])
    with_kinds = {c.mutation_kind for c in forge_candidates(matrix_with).candidates}
    without_kinds = {c.mutation_kind for c in forge_candidates(matrix_without).candidates}
    assert "IGNORE_DEPENDENCY_TRUTH" in with_kinds
    assert "IGNORE_DEPENDENCY_TRUTH" not in without_kinds


def test_forge_is_deterministic(tmp_path: Path) -> None:
    matrix = _write(
        tmp_path / "trans.yaml",
        [
            _good_pattern(pattern_id="P3_DYNAMIC_NULL_MODEL"),
            _good_pattern(pattern_id="P4_GLOBAL_PARITY_WITNESS"),
        ],
    )
    a = forge_candidates(matrix).to_dict()
    b = forge_candidates(matrix).to_dict()
    assert a == b


def test_forge_candidates_are_frozen(tmp_path: Path) -> None:
    import pytest

    matrix = _write(
        tmp_path / "trans.yaml",
        [_good_pattern(pattern_id="P4_GLOBAL_PARITY_WITNESS")],
    )
    candidate = forge_candidates(matrix).candidates[0]
    with pytest.raises(Exception):  # noqa: B017
        candidate.target_token = "evil"  # type: ignore[misc]


def test_forge_does_not_apply_mutations(tmp_path: Path) -> None:
    """The forge must not mutate any source file. Snapshot module mtime."""
    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / "geosync_hpc" / "coherence" / "global_parity_witness.py"
    if not target.exists():
        return
    mtime_before = target.stat().st_mtime
    forge_candidates(repo_root / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml")
    mtime_after = target.stat().st_mtime
    assert mtime_before == mtime_after


def test_live_translation_emits_at_least_ten_candidates() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    matrix = repo_root / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
    report = forge_candidates(matrix)
    # 10 implemented patterns + 1 cross-cutting = at least 11.
    assert len(report.candidates) >= 11
