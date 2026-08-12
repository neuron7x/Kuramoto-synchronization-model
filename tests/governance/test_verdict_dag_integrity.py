# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integrity guard for the D-002J verdict DAG bootstrap (P2.5).

Every test in this module guards one structural invariant of the
``artifacts/governance/verdicts/`` capsule set; together they fail
closed if any future PR drifts the DAG away from the four locked
transition rules (acyclic; P1A retained as REJECTED; P1B repairs
P1A; P2 parent is P1B not P1A directly).

The DAG metadata itself (``d002j_verdict_dag_v1.json``) is loaded via
``json`` rather than the capsule loader because it carries a
different schema (``D002J-VERDICT-DAG-v1``) and is excluded from
``load_dag`` by design.

All multi-line asserts use the msg-var idiom (``msg = ...`` extracted
above the ``assert``) to render byte-identically under both black and
ruff-format, which disagree on the parenthesised-message style.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from tools.governance.render_lineage import render_lineage, write_lineage
from tools.governance.verdict_dag import (
    CAPSULE_GLOB,
    LOCKED_GOVERNANCE_SHAS,
    REPO_ROOT,
    VERDICTS_DIR_REL,
    VerdictCapsule,
    check_acyclic,
    detect_orphans,
    load_capsule,
    load_dag,
    topological_order,
)

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

VERDICTS_DIR: Path = REPO_ROOT / VERDICTS_DIR_REL
DAG_VERDICT_PATH: Path = VERDICTS_DIR / "d002j_verdict_dag_v1.json"
EXPECTED_PHASES: tuple[str, ...] = (
    "P0",
    "P1",
    "P1A",
    "P1B",
    "P2",
    "P3",
    "P4",
    "P5",
    "P6",
    "P7",
)
EXPECTED_NODE_IDS: tuple[str, ...] = (
    "D002J-P0",
    "D002J-P1",
    "D002J-P1A",
    "D002J-P1B",
    "D002J-P2",
    "D002J-P3",
    "D002J-P4",
    "D002J-P5",
    "D002J-P6",
    "D002J-P7",
    # D-002K fresh lineage root. Parent is D002J-P7: D-002K exists
    # BECAUSE D-002J-P7 terminally refused (effect_too_small); this is
    # a fresh-restart descent, NOT a rescue. D-002J-P7 stays
    # TERMINAL_REFUSED and retained.
    "D002K-P0",
    # D-002K-P1 source & observable contract. Parent is D002K-P0;
    # binds the 6 P0-locked observable families to P1B-surviving
    # funding-liquidity sources x {CW3,CW4,CW5}. Narrow by design;
    # D-002J-P1A + D-002J-P7 stay TERMINAL_REJECTED/REFUSED retained.
    "D002K-P1",
    # D-002K-P2 matched placebo window registry. Parent is D002K-P1;
    # deterministic seed-locked selection of n_placebo_per_crisis
    # (K-P0 lock) matched NON-crisis placebos per CW3/CW4/CW5, zero
    # overlap with any of the six D-002J registered windows. No
    # scoring; D-002J-P1A + D-002J-P7 stay retained; canon false.
    "D002K-P2",
    # D-002K-P3 high-SNR event-transition metric layer. Parent is
    # D002K-P2; locks the executable contract for the single K-P0
    # primary confirmatory endpoint (pre_post_standardized_mean_shift)
    # plus the six exploratory_only secondary metrics. Definitions
    # only: no scoring on real data, numeric threshold deferred to the
    # power gate; D-002J-P1A + D-002J-P7 stay retained; canon false.
    "D002K-P3",
    # D-002K-P4 power-first gate before the event-conditioned run.
    # Parent is D002K-P3. Truth point of D-002K: at the K-P0-locked
    # Bonferroni alpha (0.05/3, the legitimate consequence of fewer
    # PRE-REGISTERED hypotheses, NOT a relaxation of D-002J-P7's
    # 0.05/102 at fixed scope) the conservative funding-liquidity
    # effect prior (d=0.80, NOT inflated) reaches power 0.0481 at the
    # feasible event-conditioned sample (crisis-side n1=1 per window;
    # crisis windows happen once) -- far below the 0.8 target. Honest
    # POWER_GATE_REFUSED_UNDERPOWERED, TERMINAL_REFUSED, retained as a
    # truthful negative alongside D-002J-P1A + D-002J-P7. Lineage halts
    # at P4; next legal node is a fresh D-002L pre-registration, NOT P5
    # and NOT a D-002J resurrection. D-002J stays REFUSED; canon false.
    "D002K-P4",
)

# Mirrors ``tests/governance/test_no_unresolved_merge_markers.py::_MARKER``.
_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


@pytest.fixture(scope="module")
def dag() -> dict[str, VerdictCapsule]:
    """Return the on-disk verdict capsule DAG."""
    return load_dag(VERDICTS_DIR)


@pytest.fixture(scope="module")
def dag_verdict() -> dict[str, object]:
    """Return the parsed DAG-about-the-DAG verdict JSON."""
    with DAG_VERDICT_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    msg = f"dag verdict at {DAG_VERDICT_PATH} must be a JSON object; got {type(payload).__name__}"
    assert isinstance(payload, dict), msg
    return payload


# ---------------------------------------------------------------------------
# 1. All phases P0..P2 have verdict capsules
# ---------------------------------------------------------------------------


def test_all_phases_p0_p2_have_verdict_capsules(dag: dict[str, VerdictCapsule]) -> None:
    actual_nodes = sorted(dag.keys())
    expected_nodes = sorted(EXPECTED_NODE_IDS)
    msg_nodes = f"DAG nodes mismatch: expected {expected_nodes}, got {actual_nodes}"
    assert actual_nodes == expected_nodes, msg_nodes
    actual_phases = sorted({c.phase for c in dag.values()})
    expected_phases = sorted(EXPECTED_PHASES)
    msg_phases = f"DAG phases mismatch: expected {expected_phases}, got {actual_phases}"
    assert actual_phases == expected_phases, msg_phases


# ---------------------------------------------------------------------------
# 2. DAG acyclic
# ---------------------------------------------------------------------------


def test_dag_is_acyclic(dag: dict[str, VerdictCapsule]) -> None:
    # check_acyclic raises on cycles; calling it twice is idempotent.
    check_acyclic(dag)
    check_acyclic(dag)
    order = topological_order(dag)
    msg = f"topological_order visited {len(order)} of {len(dag)} nodes (cycle suspected)"
    assert len(order) == len(dag), msg


# ---------------------------------------------------------------------------
# 3. Topological order matches phase sequence
# ---------------------------------------------------------------------------


def test_dag_topological_order_matches_phase_sequence(
    dag: dict[str, VerdictCapsule],
) -> None:
    order = topological_order(dag)
    expected = list(EXPECTED_NODE_IDS)
    msg = f"topological order mismatch: expected {expected}, got {order}"
    assert order == expected, msg
    indices = {nid: i for i, nid in enumerate(order)}
    for nid, capsule in dag.items():
        for parent in capsule.parent_nodes:
            edge_msg = (
                f"node {nid!r} (idx {indices[nid]}) precedes its parent "
                f"{parent!r} (idx {indices[parent]})"
            )
            assert indices[parent] < indices[nid], edge_msg


# ---------------------------------------------------------------------------
# 4. P1A retained as TERMINAL_REJECTED
# ---------------------------------------------------------------------------


def test_p1a_rejected_retained_as_terminal_rejected(
    dag: dict[str, VerdictCapsule],
) -> None:
    p1a = dag["D002J-P1A"]
    msg_status = f"P1A status must be TERMINAL_REJECTED, got {p1a.status!r}"
    assert p1a.status == "TERMINAL_REJECTED", msg_status
    msg_decision = f"P1A decision must be SOURCE_REGISTRY_REJECTED, got {p1a.decision!r}"
    assert p1a.decision == "SOURCE_REGISTRY_REJECTED", msg_decision


# ---------------------------------------------------------------------------
# 5. P1A failure_retention non-empty
# ---------------------------------------------------------------------------


def test_p1a_failure_retention_non_empty(dag: dict[str, VerdictCapsule]) -> None:
    p1a = dag["D002J-P1A"]
    msg_present = "P1A failure_retention must not be null for a TERMINAL_REJECTED node"
    assert p1a.failure_retention is not None, msg_present
    msg_str = f"P1A failure_retention must be a non-empty string, got {p1a.failure_retention!r}"
    assert isinstance(p1a.failure_retention, str) and p1a.failure_retention.strip(), msg_str


# ---------------------------------------------------------------------------
# 6. P1A allowed_next_nodes includes the repair path P1B
# ---------------------------------------------------------------------------


def test_p1a_allowed_next_includes_p1b_repair_path(
    dag: dict[str, VerdictCapsule],
) -> None:
    p1a = dag["D002J-P1A"]
    msg_allow = f"P1A must allow D002J-P1B as repair path; allowed={list(p1a.allowed_next_nodes)}"
    assert "D002J-P1B" in p1a.allowed_next_nodes, msg_allow
    msg_forbid = f"P1A must forbid skipping to D002J-P2; forbidden={list(p1a.forbidden_next_nodes)}"
    assert "D002J-P2" in p1a.forbidden_next_nodes, msg_forbid


# ---------------------------------------------------------------------------
# 7. P1B parent includes P1A
# ---------------------------------------------------------------------------


def test_p1b_parent_includes_p1a(dag: dict[str, VerdictCapsule]) -> None:
    p1b = dag["D002J-P1B"]
    msg_parent = (
        f"P1B must declare D002J-P1A as parent (repair lineage); got {list(p1b.parent_nodes)}"
    )
    assert "D002J-P1A" in p1b.parent_nodes, msg_parent
    msg_decision = f"P1B decision must be SOURCE_REGISTRY_PARTIALLY_VERIFIED, got {p1b.decision!r}"
    assert p1b.decision == "SOURCE_REGISTRY_PARTIALLY_VERIFIED", msg_decision


# ---------------------------------------------------------------------------
# 8. P2 parent is P1B, not P1A directly
# ---------------------------------------------------------------------------


def test_p2_parent_is_p1b_not_p1a_directly(dag: dict[str, VerdictCapsule]) -> None:
    p2 = dag["D002J-P2"]
    msg_exact = f"P2 parent_nodes must be exactly ('D002J-P1B',), got {list(p2.parent_nodes)}"
    assert p2.parent_nodes == ("D002J-P1B",), msg_exact
    msg_excl = f"P2 must not list P1A directly as a parent; got {list(p2.parent_nodes)}"
    assert "D002J-P1A" not in p2.parent_nodes, msg_excl


# ---------------------------------------------------------------------------
# 9. P2 allowed_next includes P2.5 and P3
# ---------------------------------------------------------------------------


def test_p2_allowed_next_includes_p25_and_p3(dag: dict[str, VerdictCapsule]) -> None:
    p2 = dag["D002J-P2"]
    msg_25 = f"P2 must allow D002J-P2.5 as next; allowed={list(p2.allowed_next_nodes)}"
    assert "D002J-P2.5" in p2.allowed_next_nodes, msg_25
    msg_3 = f"P2 must allow D002J-P3 as next; allowed={list(p2.allowed_next_nodes)}"
    assert "D002J-P3" in p2.allowed_next_nodes, msg_3


# ---------------------------------------------------------------------------
# 10. Canonical run is not authorized anywhere in the DAG
# ---------------------------------------------------------------------------


def test_canonical_run_not_authorized_anywhere_in_dag(
    dag: dict[str, VerdictCapsule],
    dag_verdict: dict[str, object],
) -> None:
    flag = dag_verdict["canonical_run_authorized_anywhere"]
    msg_flag = f"DAG verdict must declare canonical_run_authorized_anywhere=False; got {flag!r}"
    assert flag is False, msg_flag
    for nid, capsule in dag.items():
        msg_node = (
            f"node {nid!r} claim_boundary must encode the no-canonical-run "
            f"invariant (looked for 'canonical_run_authorized' or "
            f"'no canonical run' or 'does NOT authorise'); "
            f"got {capsule.claim_boundary!r}"
        )
        boundary = capsule.claim_boundary.lower()
        encoded = (
            "canonical_run_authorized" in boundary
            or "no canonical run" in boundary
            or "does not authorise" in boundary
            or "does not rescue" in boundary
            or "no canonical run authorization" in boundary
        )
        assert encoded, msg_node


# ---------------------------------------------------------------------------
# 11. DAG self-verdict present
# ---------------------------------------------------------------------------


def test_dag_self_verdict_present(dag_verdict: dict[str, object]) -> None:
    self_verdict = dag_verdict.get("dag_self_verdict")
    msg_type = f"dag_self_verdict must be a JSON object; got {type(self_verdict).__name__}"
    assert isinstance(self_verdict, dict), msg_type
    msg_node = f"dag_self_verdict.node_id must be 'D002J-P2.5'; got {self_verdict.get('node_id')!r}"
    assert self_verdict.get("node_id") == "D002J-P2.5", msg_node
    msg_decision = (
        f"dag_self_verdict.decision must be 'VERDICT_DAG_BOOTSTRAPPED'; "
        f"got {self_verdict.get('decision')!r}"
    )
    assert self_verdict.get("decision") == "VERDICT_DAG_BOOTSTRAPPED", msg_decision


# ---------------------------------------------------------------------------
# 12. No orphan nodes
# ---------------------------------------------------------------------------


def test_no_orphan_nodes(dag: dict[str, VerdictCapsule]) -> None:
    orphans = detect_orphans(dag)
    msg_zero = f"DAG must contain no orphan nodes; detect_orphans returned {orphans}"
    assert orphans == [], msg_zero
    # Cross-check via direct iteration so the test does not depend solely
    # on detect_orphans being correct.
    parents = {p for c in dag.values() for p in c.parent_nodes}
    unknown = sorted(parents - set(dag))
    msg_unknown = f"Some parent_nodes reference unknown ids: {unknown}"
    assert parents.issubset(set(dag)), msg_unknown


# ---------------------------------------------------------------------------
# 13. All capsule JSONs parse via load_capsule
# ---------------------------------------------------------------------------


def test_all_capsule_jsons_parse_via_load_capsule() -> None:
    files = sorted(VERDICTS_DIR.glob(CAPSULE_GLOB))
    msg_count = (
        f"expected {len(EXPECTED_NODE_IDS)} capsule files under {VERDICTS_DIR}; found {len(files)}"
    )
    assert len(files) == len(EXPECTED_NODE_IDS), msg_count
    parsed: list[VerdictCapsule] = []
    for f in files:
        capsule = load_capsule(f)
        parsed.append(capsule)
        msg_schema = (
            f"{f.name}: schema_version must be 'D002J-VERDICT-CAPSULE-v1'; "
            f"got {capsule.schema_version!r}"
        )
        assert capsule.schema_version == "D002J-VERDICT-CAPSULE-v1", msg_schema
    node_ids = sorted(c.node_id for c in parsed)
    expected = sorted(EXPECTED_NODE_IDS)
    msg_ids = f"parsed node_ids mismatch: expected {expected}, got {node_ids}"
    assert node_ids == expected, msg_ids


# ---------------------------------------------------------------------------
# 14. Lineage map MD renders deterministically (idempotent)
# ---------------------------------------------------------------------------


def test_lineage_map_md_renders_deterministically(tmp_path: Path) -> None:
    # Copy the verdict capsules into an isolated tmp dir, then render
    # twice and assert byte equality.
    tmp_verdicts = tmp_path / "verdicts"
    tmp_verdicts.mkdir()
    for f in sorted(VERDICTS_DIR.glob(CAPSULE_GLOB)):
        shutil.copy2(f, tmp_verdicts / f.name)
    out1 = tmp_path / "render1.md"
    out2 = tmp_path / "render2.md"
    write_lineage(tmp_verdicts, out1)
    write_lineage(tmp_verdicts, out2)
    b1 = out1.read_bytes()
    b2 = out2.read_bytes()
    msg_bytes = (
        f"render_lineage must be byte-identical across runs; "
        f"hash1={hashlib.sha256(b1).hexdigest()} "
        f"hash2={hashlib.sha256(b2).hexdigest()}"
    )
    assert b1 == b2, msg_bytes
    body = render_lineage(tmp_verdicts)
    msg_str = "render_lineage(...) string return must match write_lineage(...) bytes"
    assert body.encode("utf-8") == b1, msg_str


# ---------------------------------------------------------------------------
# 15. Locked governance SHAs byte-exact
# ---------------------------------------------------------------------------


def test_locked_governance_shas_byte_exact() -> None:
    mismatches: list[tuple[str, str, str]] = []
    for rel, expected in LOCKED_GOVERNANCE_SHAS.items():
        path = REPO_ROOT / rel
        msg_present = f"locked governance file missing: {path}"
        assert path.is_file(), msg_present
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append((rel, expected, actual))
    msg_drift = f"locked governance sha256 drift detected; mismatches={mismatches}"
    assert not mismatches, msg_drift


# ---------------------------------------------------------------------------
# 16. No unresolved merge markers in any new file
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets: list[Path] = []
    targets.extend(sorted(VERDICTS_DIR.glob("d002[jk]_*verdict*v1.json")))
    targets.append(REPO_ROOT / "tools/governance/verdict_dag.py")
    targets.append(REPO_ROOT / "tools/governance/render_lineage.py")
    targets.append(REPO_ROOT / "tests/governance/test_verdict_dag_integrity.py")
    targets.append(REPO_ROOT / "docs/research/D002J_LINEAGE_MAP.md")
    targets.append(REPO_ROOT / "docs/governance/D002G_CANONICAL_RUN_BLOCKERS.md")
    hits: list[tuple[str, int, str]] = []
    for p in targets:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _MARKER.match(line):
                hits.append((str(p.relative_to(REPO_ROOT)), i, line[:32]))
    msg = f"unresolved git-merge markers detected in DAG-touching files: {hits}"
    assert hits == [], msg
