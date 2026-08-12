# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml

from governance.evidence_graph import build_evidence_graph


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, Any]:
    module = tmp_path / "analytics/signals/demo.py"
    _write(
        module,
        '''
        CLAIM_BOUNDARY = "descriptor_only_not_predictor"

        def measure() -> str:
            return CLAIM_BOUNDARY
        ''',
    )
    test_file = tmp_path / "tests/unit/analytics/test_demo.py"
    _write(test_file, "def test_demo():\n    assert True\n")
    acceptor = tmp_path / ".claude/commit_acceptors/demo.yaml"
    _write(
        acceptor,
        '''
        diff_scope:
          changed_files:
            - path: analytics/signals/demo.py
        evidence:
          - path: tmp/demo.log
            sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        ''',
    )
    return {
        "schema_version": 1,
        "claim_boundary_required": "descriptor_only_not_predictor",
        "instruments": [
            {
                "id": "demo",
                "pr": 1,
                "merge_commit": "0" * 40,
                "module": "analytics/signals/demo.py",
                "source_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
                "test_file": "tests/unit/analytics/test_demo.py",
                "acceptor": ".claude/commit_acceptors/demo.yaml",
                "claim_boundary": "descriptor_only_not_predictor",
                "falsifiers": ["tests/unit/analytics/test_demo.py::test_demo"],
            }
        ],
    }


def _instrument(registry: dict[str, Any]) -> dict[str, Any]:
    instruments = registry["instruments"]
    assert isinstance(instruments, list)
    item = instruments[0]
    assert isinstance(item, dict)
    return item


def test_builds_machine_readable_graph_without_negative_evidence(tmp_path: Path) -> None:
    graph = build_evidence_graph(_fixture(tmp_path), root=tmp_path)

    assert graph["dangling_nodes"] == []
    assert graph["stale_hashes"] == []
    assert graph["missing_tests"] == []
    assert graph["missing_acceptors"] == []
    assert graph["missing_artifacts"] == []
    assert graph["claim_boundary_violations"] == []
    assert {node["kind"] for node in graph["nodes"]} >= {
        "instrument",
        "module",
        "test_file",
        "acceptor",
        "artifact",
        "pytest_node",
    }
    assert any(edge["relation"] == "falsified_by" for edge in graph["edges"])


def test_missing_test_is_preserved_as_negative_evidence(tmp_path: Path) -> None:
    registry = _fixture(tmp_path)
    Path(tmp_path / "tests/unit/analytics/test_demo.py").unlink()

    graph = build_evidence_graph(registry, root=tmp_path)

    assert graph["missing_tests"] == [
        {"instrument": "demo", "test_file": "tests/unit/analytics/test_demo.py"}
    ]


def test_source_hash_drift_is_reported(tmp_path: Path) -> None:
    registry = _fixture(tmp_path)
    _instrument(registry)["source_sha256"] = "b" * 64

    graph = build_evidence_graph(registry, root=tmp_path)

    assert graph["stale_hashes"][0]["instrument"] == "demo"
    assert graph["stale_hashes"][0]["expected"] == "b" * 64


def test_claim_boundary_violation_is_reported(tmp_path: Path) -> None:
    registry = _fixture(tmp_path)
    _instrument(registry)["claim_boundary"] = "predictive"

    graph = build_evidence_graph(registry, root=tmp_path)

    assert graph["claim_boundary_violations"] == [
        {"instrument": "demo", "module": "analytics/signals/demo.py", "boundary": "predictive"}
    ]


def test_registry_shape_is_serializable(tmp_path: Path) -> None:
    graph = build_evidence_graph(_fixture(tmp_path), root=tmp_path)
    dumped = yaml.safe_dump(graph, sort_keys=True)

    assert "dangling_nodes" in dumped
    assert "claim_boundary_violations" in dumped
