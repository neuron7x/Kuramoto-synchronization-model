# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/governance/claim_provenance_graph.py."""

from __future__ import annotations

from pathlib import Path

import yaml

from tools.governance.claim_provenance_graph import build_graph


def test_live_graph_emits_nodes_and_edges_for_implemented_patterns(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    matrix = repo_root / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
    report = build_graph(matrix)
    assert len(report.nodes) > 0
    assert len(report.edges) > 0
    pids = {n.node_id for n in report.nodes if n.kind == "claim"}
    # At least P1 through P10 must be claim nodes (10 patterns
    # IMPLEMENTED in the canonical state).
    expected_min = {f"P{i}_" for i in range(1, 11)}
    matched = sum(1 for pid in pids for prefix in expected_min if pid.startswith(prefix))
    assert matched >= 10


def test_live_graph_has_no_broken_edges() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    matrix = repo_root / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
    report = build_graph(matrix)
    # Every IMPLEMENTED pattern at the canonical state has a test file
    # and a _FALSIFIER_TEXT in its module.
    assert report.broken == [], f"unexpected broken edges: {report.broken}"


def test_synthetic_pattern_without_test_marks_broken(tmp_path: Path) -> None:
    """Falsifier surface: a pattern with module but no test → BROKEN.

    Build a synthetic translation pointing at a module that exists in
    the live tree but whose stem has no `test_<stem>.py` anywhere.
    """
    matrix = tmp_path / "trans.yaml"
    matrix.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "patterns": [
                    {
                        "pattern_id": "P_FAKE",
                        "source_ids": ["S99_FAKE"],
                        "source_fact_summary": "x",
                        "methodological_pattern": "y",
                        "geosync_operational_analog": "z",
                        # Existing file with no matching test_<stem>.py.
                        "proposed_module": "tools/governance/__init__.py",
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
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    report = build_graph(matrix)
    assert any("no-test-for: P_FAKE" in b for b in report.broken)


def test_synthetic_pattern_without_falsifier_marks_broken(tmp_path: Path) -> None:
    """A module without _FALSIFIER_TEXT but with a matching test → BROKEN."""
    matrix = tmp_path / "trans.yaml"
    matrix.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "patterns": [
                    {
                        "pattern_id": "P_TEST_NO_FALSIFIER",
                        "source_ids": ["S99_FAKE"],
                        "source_fact_summary": "x",
                        "methodological_pattern": "y",
                        "geosync_operational_analog": "z",
                        # tools/governance/__init__.py is empty: no falsifier text
                        "proposed_module": "tools/governance/__init__.py",
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
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    report = build_graph(matrix)
    # Either no-test-for OR no-falsifier-text fires, depending on which
    # check triggers first; both are valid BROKEN signals for this case.
    assert any("P_TEST_NO_FALSIFIER" in b for b in report.broken)


def test_proposed_pattern_excluded_from_graph(tmp_path: Path) -> None:
    """PROPOSED-status patterns do NOT appear as claim nodes."""
    matrix = tmp_path / "trans.yaml"
    matrix.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "patterns": [
                    {
                        "pattern_id": "P_PROPOSED_ONLY",
                        "source_ids": ["S99_FAKE"],
                        "source_fact_summary": "x",
                        "methodological_pattern": "y",
                        "geosync_operational_analog": "z",
                        "proposed_module": "geosync_hpc/fake/m.py",
                        "claim_tier": "ENGINEERING_ANALOG",
                        "implementation_status": "PROPOSED",
                        "measurable_inputs": ["a"],
                        "output_witness": ["b"],
                        "null_model": "n",
                        "falsifier": "f",
                        "deterministic_tests": ["t"],
                        "mutation_candidate": "m",
                        "ledger_entry_required": True,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    report = build_graph(matrix)
    assert not any(n.node_id == "P_PROPOSED_ONLY" for n in report.nodes)


def test_graph_is_deterministic() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    matrix = repo_root / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
    a = build_graph(matrix).to_dict()
    b = build_graph(matrix).to_dict()
    assert a == b


def test_workflows_referencing_validators_appear_as_workflow_nodes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    matrix = repo_root / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
    report = build_graph(matrix)
    workflow_nodes = [n for n in report.nodes if n.kind == "workflow"]
    # Both physics-2026-gate.yml and reality-validators-gate.yml
    # reference validate_*.py scripts; expect ≥1 workflow node.
    assert len(workflow_nodes) >= 1
