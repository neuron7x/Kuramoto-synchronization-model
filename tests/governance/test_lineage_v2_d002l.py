# Copyright (c) 2023-2026 Yaroslav Vasylenko
# SPDX-License-Identifier: MIT
"""D-002 lineage v2 governance tests for the J -> K -> L restart chain."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.governance.lineage_v2 import (
    LineageV2Error,
    build_payload,
    cross_lineage_transitions,
    discover_capsules,
    lineage_id,
    load_connected_dag,
    next_legal_nodes,
    render_markdown,
)
from tools.governance.verdict_dag import VERDICTS_DIR_REL

REPO_ROOT = Path(__file__).resolve().parents[2]
VERDICTS = REPO_ROOT / VERDICTS_DIR_REL
SNAPSHOT = VERDICTS / "d002_lineage_dag_v2.json"


def test_discovery_includes_j_k_l_capsules_only() -> None:
    names = [p.name for p in discover_capsules(VERDICTS)]
    assert "d002j_p7_verdict_v1.json" in names
    assert "d002k_p4_verdict_v1.json" in names
    assert "d002l_p0_verdict_v1.json" in names
    assert "d002j_verdict_dag_v1.json" not in names
    assert "d002_lineage_dag_v2.json" not in names


def test_connected_dag_has_16_nodes_and_no_orphan() -> None:
    dag = load_connected_dag(VERDICTS)
    assert len(dag) == 16
    assert dag["D002L-P0"].parent_nodes == ("D002K-P4",)


def test_parent_refusals_remain_terminal() -> None:
    dag = load_connected_dag(VERDICTS)
    assert dag["D002J-P7"].status == "TERMINAL_REFUSED"
    assert dag["D002K-P4"].status == "TERMINAL_REFUSED"
    assert dag["D002L-P0"].status == "TERMINAL_PASS"


def test_cross_lineage_transitions_are_fresh_non_rescues() -> None:
    dag = load_connected_dag(VERDICTS)
    transitions = cross_lineage_transitions(dag)
    assert transitions == {
        "D002J-P7": {
            "status": "TERMINAL_REFUSED",
            "successor_lineage": "D-002K",
            "successor_root": "D002K-P0",
            "is_rescue": False,
        },
        "D002K-P4": {
            "status": "TERMINAL_REFUSED",
            "successor_lineage": "D-002L",
            "successor_root": "D002L-P0",
            "is_rescue": False,
        },
    }


def test_only_next_legal_node_is_d002l_p1() -> None:
    dag = load_connected_dag(VERDICTS)
    assert next_legal_nodes(dag) == ["D002L-P1"]


def test_payload_matches_locked_semantic_snapshot() -> None:
    dag = load_connected_dag(VERDICTS)
    computed = build_payload(dag, generated_at="2026-08-28T00:00:00Z")
    locked = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert computed == locked


def test_payload_never_authorizes_canonical_run() -> None:
    dag = load_connected_dag(VERDICTS)
    payload = build_payload(dag, generated_at="CHECK")
    assert payload["canonical_run_authorized_anywhere"] is False
    assert "does not prove scientific validity" in payload["claim_boundary"]


def test_lineage_id_is_generic() -> None:
    assert lineage_id("D002J-P7") == "D-002J"
    assert lineage_id("D002K-P4") == "D-002K"
    assert lineage_id("D002L-P0") == "D-002L"
    with pytest.raises(LineageV2Error):
        lineage_id("BROKEN-P0")


def test_cross_lineage_restart_from_pass_parent_is_refused() -> None:
    dag = load_connected_dag(VERDICTS)
    original = dag["D002L-P0"]
    from dataclasses import replace

    dag["D002L-P0"] = replace(original, parent_nodes=("D002K-P3",))
    with pytest.raises(LineageV2Error, match="requires rejected/refused parent"):
        cross_lineage_transitions(dag)


def test_duplicate_node_id_is_refused(tmp_path: Path) -> None:
    source = VERDICTS / "d002l_p0_verdict_v1.json"
    body = source.read_text(encoding="utf-8")
    (tmp_path / "d002l_p0_verdict_v1.json").write_text(body, encoding="utf-8")
    (tmp_path / "d002m_p0_verdict_v1.json").write_text(body, encoding="utf-8")
    with pytest.raises(LineageV2Error, match="duplicate node_id"):
        load_connected_dag(tmp_path)


def test_render_exposes_both_fresh_restart_edges() -> None:
    text = render_markdown(load_connected_dag(VERDICTS))
    assert "D002J-P7" in text
    assert "D002K-P0" in text
    assert "D002K-P4" in text
    assert "D002L-P0" in text
    assert "is_rescue=false" in text
    assert "D002L-P1" in text
