# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verdict DAG load / parse / validate / walk for D-002J governance lineage.

This module converts the narrative "per-phase fail-closed kernel" used across
D-002J PR briefs into an explicit compositional algebra over verdict capsules.

A *verdict capsule* is a canonical JSON document emitted by a phase-shipping
PR; it summarises the phase's terminal verdict (PASS / PARTIAL / REJECTED /
REFUSED), the artifacts retained, the next legal nodes, and the forbidden
next nodes. The DAG is the topologically-ordered collection of capsules.

The module is governance infrastructure — it does not import any physics,
research, or trading code; it does not execute any canonical run; it does
not promote any claim. It is the machine-verifiable substrate that future
phases (P3..P9) plug into.

CLI
---

    python -m tools.governance.verdict_dag check
        Validates the DAG (acyclic, no orphans, schemas valid, locked SHAs
        byte-exact) and exits non-zero on any failure.

    python -m tools.governance.verdict_dag emit
        Writes ``artifacts/governance/verdicts/d002j_verdict_dag_v1.json``
        from the current capsule set on disk.

    python -m tools.governance.verdict_dag render
        Delegates to :mod:`tools.governance.render_lineage` which writes
        ``docs/research/D002J_LINEAGE_MAP.md``.

The shapes (``VerdictCapsule``) are frozen dataclasses; canonical JSON
serialisation uses ``sort_keys=True, indent=2``. Locked governance SHAs
are pinned in :data:`LOCKED_GOVERNANCE_SHAS` and verified byte-exact on
every ``check`` invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# Constants & repo anchors
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
"""Absolute path to the GeoSync repo root (two parents above this file)."""

VERDICTS_DIR_REL: Final[str] = "artifacts/governance/verdicts"
"""Relative directory holding the per-phase verdict capsule JSONs."""

DAG_OUTPUT_REL: Final[str] = "artifacts/governance/verdicts/d002j_verdict_dag_v1.json"
"""Relative path to the DAG-about-the-DAG verdict (recursive self-anchor)."""

SCHEMA_CAPSULE: Final[str] = "D002J-VERDICT-CAPSULE-v1"
"""Required ``schema_version`` value on every capsule."""

SCHEMA_DAG: Final[str] = "D002J-VERDICT-DAG-v1"
"""Required ``schema_version`` value on the DAG artifact."""

VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {"TERMINAL_PASS", "TERMINAL_PARTIAL", "TERMINAL_REJECTED", "TERMINAL_REFUSED"},
)
"""The four terminal status values a capsule may declare."""

REQUIRED_CAPSULE_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "node_id",
    "phase",
    "pr_number",
    "merge_sha",
    "parent_nodes",
    "decision",
    "status",
    "artifact_paths",
    "test_paths",
    "allowed_next_nodes",
    "forbidden_next_nodes",
    "claim_boundary",
    "failure_retention",
    "source_summary_path",
)
"""Top-level fields every capsule JSON document must carry."""

LOCKED_GOVERNANCE_SHAS: Final[dict[str, str]] = {
    "docs/governance/D002C_CLAIM_LEDGER.yaml": "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387",  # pragma: allowlist secret
    "docs/governance/D002G_PREREGISTRATION.yaml": "1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04",  # pragma: allowlist secret
    "docs/governance/D002G_ACCEPTANCE_RULES.md": "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31",  # pragma: allowlist secret
    "docs/governance/D002H_PREREGISTRATION.yaml": "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec",  # pragma: allowlist secret
    "docs/governance/D002I_PREREGISTRATION.yaml": "b646989c032dc0e29f9b791e0b68209ff22b40f4757737712badc8656cf2db5f",  # pragma: allowlist secret
    "docs/governance/D002J_PREREGISTRATION.yaml": "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0",  # pragma: allowlist secret
}
"""Pinned byte-exact SHAs for the six locked governance anchors.

Names map to file paths; values are sha256 hex digests. The ``check``
subcommand fails closed if any anchor on disk diverges from these values.
"""

# Decision-string -> status mapping (case-insensitive on suffix).
_DECISION_STATUS_MAP: Final[dict[str, str]] = {
    "VERIFIED": "TERMINAL_PASS",
    "READY": "TERMINAL_PASS",
    "LOCKED": "TERMINAL_PASS",
    "BOOTSTRAPPED": "TERMINAL_PASS",
    "PARTIALLY_VERIFIED": "TERMINAL_PARTIAL",
    "REJECTED": "TERMINAL_REJECTED",
    "REPAIR_FAILED": "TERMINAL_REJECTED",
    "REFUSED": "TERMINAL_REFUSED",
    # D-002J-P7 power-first gate honest refusal terminal: an
    # underpowered canonical-run gate is a TERMINAL_REFUSED retained
    # negative artifact (same canon as a bare _REFUSED), not a PASS.
    "REFUSED_UNDERPOWERED": "TERMINAL_REFUSED",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class VerdictDAGError(Exception):
    """Base class for every fail-closed error this module raises."""


class CycleDetected(VerdictDAGError):
    """Raised when DAG validation finds a cycle (refuses topological sort)."""


class OrphanNode(VerdictDAGError):
    """Raised when a node's ``parent_nodes`` reference an unknown node id."""


class IllegalTransition(VerdictDAGError):
    """Raised when a requested ``from->to`` move is not in ``allowed_next_nodes``."""


class MissingCapsule(VerdictDAGError):
    """Raised when a required capsule JSON file is missing on disk."""


class SchemaViolation(VerdictDAGError):
    """Raised when a capsule JSON fails the canonical schema check."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerdictCapsule:
    """Immutable, frozen representation of one phase's terminal verdict.

    Field semantics:

    * ``schema_version``: must equal :data:`SCHEMA_CAPSULE`.
    * ``node_id``: globally unique id of the phase node (e.g. ``D002J-P1``).
    * ``phase``: short phase tag (``P0``, ``P1``, ``P1A``, ``P1B``, ``P2``,
      ``P2.5``...).
    * ``pr_number``: integer PR number on GitHub.
    * ``merge_sha``: 40-char hex sha at which the phase landed on ``main``.
    * ``parent_nodes``: tuple of upstream node ids this node depends on.
    * ``decision``: human / machine readable decision string (e.g.
      ``DATA_REGISTRY_READY``).
    * ``status``: one of :data:`VALID_STATUSES`.
    * ``artifact_paths``: tuple of repo-relative artifact paths retained.
    * ``test_paths``: tuple of repo-relative test paths covering this phase.
    * ``allowed_next_nodes``: tuple of node ids this node permits as successors.
    * ``forbidden_next_nodes``: tuple of node ids explicitly forbidden as
      successors (e.g. gate-skipping shortcuts).
    * ``claim_boundary``: prose claim boundary inherited from the phase brief.
    * ``failure_retention``: None for PASS / PARTIAL nodes; non-empty prose
      for REJECTED / REFUSED nodes recording what failed and where it lives.
    * ``source_summary_path``: repo-relative path to the upstream phase
      summary artifact this capsule was backfilled from.
    """

    schema_version: str
    node_id: str
    phase: str
    pr_number: int
    merge_sha: str
    parent_nodes: tuple[str, ...]
    decision: str
    status: str
    artifact_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    allowed_next_nodes: tuple[str, ...]
    forbidden_next_nodes: tuple[str, ...]
    claim_boundary: str
    failure_retention: str | None
    source_summary_path: str

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict (tuples coerced to lists, sort-stable)."""
        raw = asdict(self)
        for k, v in raw.items():
            if isinstance(v, tuple):
                raw[k] = list(v)
        return raw


def map_decision_to_status(decision: str) -> str:
    """Return the canonical status for *decision*.

    Maps decision-string suffixes to :data:`VALID_STATUSES` per the rule
    table in the module docstring. Raises :class:`SchemaViolation` if no
    suffix matches, which is the fail-closed default.
    """
    if not isinstance(decision, str) or not decision:
        msg = f"decision must be a non-empty string, got {decision!r}"
        raise SchemaViolation(msg)
    upper = decision.strip().upper()
    # Match the LONGEST suffix first so PARTIALLY_VERIFIED (PARTIAL)
    # wins over the bare _VERIFIED prefix-match (PASS). Determinism
    # over insertion order; alpha-ordered ties for reproducibility.
    for suffix in sorted(_DECISION_STATUS_MAP, key=lambda s: (-len(s), s)):
        if upper.endswith(suffix):
            return _DECISION_STATUS_MAP[suffix]
    msg = (
        f"unmapped decision suffix in {decision!r}; known suffixes: {sorted(_DECISION_STATUS_MAP)}"
    )
    raise SchemaViolation(msg)


# ---------------------------------------------------------------------------
# Loading & validation
# ---------------------------------------------------------------------------


def _validate_capsule_dict(raw: dict[str, Any], path: Path) -> None:
    """Fail-closed schema check on a parsed capsule dict.

    Verifies every required field is present, the schema version matches,
    status is in the valid set, merge_sha is 40 hex chars, and tuple-like
    fields decode as lists. Raises :class:`SchemaViolation` on any defect.
    """
    missing = [f for f in REQUIRED_CAPSULE_FIELDS if f not in raw]
    if missing:
        msg = f"{path}: missing required capsule fields {missing}"
        raise SchemaViolation(msg)
    if raw["schema_version"] != SCHEMA_CAPSULE:
        msg = f"{path}: schema_version must be {SCHEMA_CAPSULE!r}, got {raw['schema_version']!r}"
        raise SchemaViolation(msg)
    if raw["status"] not in VALID_STATUSES:
        msg = f"{path}: status {raw['status']!r} not in {sorted(VALID_STATUSES)}"
        raise SchemaViolation(msg)
    sha = raw["merge_sha"]
    if not isinstance(sha, str) or len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
        msg = f"{path}: merge_sha must be 40-char lower-hex, got {sha!r}"
        raise SchemaViolation(msg)
    for list_field in (
        "parent_nodes",
        "artifact_paths",
        "test_paths",
        "allowed_next_nodes",
        "forbidden_next_nodes",
    ):
        v = raw[list_field]
        if not isinstance(v, list):
            msg = f"{path}: field {list_field!r} must decode as list, got {type(v).__name__}"
            raise SchemaViolation(msg)
    derived = map_decision_to_status(raw["decision"])
    if derived != raw["status"]:
        msg = (
            f"{path}: status {raw['status']!r} disagrees with decision "
            f"suffix-derived status {derived!r} for decision {raw['decision']!r}"
        )
        raise SchemaViolation(msg)
    fr = raw["failure_retention"]
    if raw["status"] in {"TERMINAL_REJECTED", "TERMINAL_REFUSED"}:
        if not isinstance(fr, str) or not fr.strip():
            msg = (
                f"{path}: failure_retention must be a non-empty string for status {raw['status']!r}"
            )
            raise SchemaViolation(msg)
    elif fr is not None:
        msg = (
            f"{path}: failure_retention must be null for status "
            f"{raw['status']!r}, got {type(fr).__name__}"
        )
        raise SchemaViolation(msg)


def load_capsule(path: Path) -> VerdictCapsule:
    """Load one capsule JSON file and return a frozen :class:`VerdictCapsule`.

    Raises:
        :class:`MissingCapsule` when *path* does not exist.
        :class:`SchemaViolation` when the file fails schema validation.
    """
    if not path.is_file():
        msg = f"capsule file does not exist: {path}"
        raise MissingCapsule(msg)
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        msg = f"{path}: top-level JSON must be an object, got {type(raw).__name__}"
        raise SchemaViolation(msg)
    _validate_capsule_dict(raw, path)
    return VerdictCapsule(
        schema_version=raw["schema_version"],
        node_id=raw["node_id"],
        phase=raw["phase"],
        pr_number=int(raw["pr_number"]),
        merge_sha=raw["merge_sha"],
        parent_nodes=tuple(raw["parent_nodes"]),
        decision=raw["decision"],
        status=raw["status"],
        artifact_paths=tuple(raw["artifact_paths"]),
        test_paths=tuple(raw["test_paths"]),
        allowed_next_nodes=tuple(raw["allowed_next_nodes"]),
        forbidden_next_nodes=tuple(raw["forbidden_next_nodes"]),
        claim_boundary=raw["claim_boundary"],
        failure_retention=raw["failure_retention"],
        source_summary_path=raw["source_summary_path"],
    )


CAPSULE_GLOB: Final[str] = "d002[jk]_p*_verdict_v1.json"
"""Glob matching per-phase capsule files across the connected D-002J /
D-002K lineages.

The DAG spans both lineages: D-002K-P0's parent is ``D002J-P7`` because
D-002K exists *because* D-002J-P7 refused. Widened from the original
``d002j_p*`` to ``d002[jk]_p*`` so the single combined DAG renders both
lineages in one honest graph. The DAG-about-the-DAG artifact
(``d002j_verdict_dag_v1.json``) is still excluded because it carries a
different schema (it ends in ``verdict_dag_v1.json``, not
``_p*_verdict_v1.json``).
"""


def load_dag(verdicts_dir: Path) -> dict[str, VerdictCapsule]:
    """Load every per-phase capsule under *verdicts_dir* into a node_id->capsule map.

    The DAG-about-the-DAG artifact (``d002j_verdict_dag_v1.json``) is
    explicitly excluded because it carries a different schema. Any
    ``d002[jk]_p*_verdict_v1.json`` file is treated as a capsule (the
    connected D-002J / D-002K lineages).

    Raises:
        :class:`MissingCapsule` when *verdicts_dir* does not exist.
    """
    if not verdicts_dir.is_dir():
        msg = f"verdicts directory does not exist: {verdicts_dir}"
        raise MissingCapsule(msg)
    dag: dict[str, VerdictCapsule] = {}
    for path in sorted(verdicts_dir.glob(CAPSULE_GLOB)):
        capsule = load_capsule(path)
        dag[capsule.node_id] = capsule
    return dag


# ---------------------------------------------------------------------------
# Graph algorithms
# ---------------------------------------------------------------------------


def check_acyclic(dag: dict[str, VerdictCapsule]) -> None:
    """Fail-closed acyclic check via Kahn's algorithm.

    Raises :class:`CycleDetected` (with the unresolved subset of node ids)
    if any cycle is present.
    """
    # Build adjacency: parent -> [children].
    indeg: dict[str, int] = {n: 0 for n in dag}
    children: dict[str, list[str]] = {n: [] for n in dag}
    for node_id, capsule in dag.items():
        for parent in capsule.parent_nodes:
            if parent not in dag:
                msg = f"node {node_id!r} references unknown parent {parent!r}"
                raise OrphanNode(msg)
            children[parent].append(node_id)
            indeg[node_id] += 1
    queue: deque[str] = deque(n for n, d in indeg.items() if d == 0)
    visited = 0
    while queue:
        n = queue.popleft()
        visited += 1
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                queue.append(c)
    if visited != len(dag):
        unresolved = sorted(n for n, d in indeg.items() if d > 0)
        msg = f"cycle detected; unresolved nodes: {unresolved}"
        raise CycleDetected(msg)


def topological_order(dag: dict[str, VerdictCapsule]) -> list[str]:
    """Return a deterministic topological order (Kahn + alpha-ordered ties).

    Calls :func:`check_acyclic` first; ties broken by lexicographic
    node_id sort so the output is stable across runs.

    Raises:
        :class:`CycleDetected` if the DAG is not acyclic.
        :class:`OrphanNode` if any parent reference is unresolved.
    """
    check_acyclic(dag)
    indeg: dict[str, int] = {n: 0 for n in dag}
    children: dict[str, list[str]] = {n: [] for n in dag}
    for node_id, capsule in dag.items():
        for parent in capsule.parent_nodes:
            children[parent].append(node_id)
            indeg[node_id] += 1
    # Initial frontier: sources with indeg == 0, alpha-sorted.
    frontier: list[str] = sorted(n for n, d in indeg.items() if d == 0)
    order: list[str] = []
    while frontier:
        n = frontier.pop(0)
        order.append(n)
        next_ready: list[str] = []
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                next_ready.append(c)
        # Merge alpha-sorted to preserve determinism.
        frontier = sorted({*frontier, *next_ready})
    return order


def detect_orphans(dag: dict[str, VerdictCapsule]) -> list[str]:
    """Return sorted node_ids whose ``parent_nodes`` reference unknown nodes.

    An *orphan* here is a node carrying a dangling parent reference, not
    a root node — roots (``parent_nodes == ()``) are legal and not flagged.
    """
    orphans: set[str] = set()
    for node_id, capsule in dag.items():
        for parent in capsule.parent_nodes:
            if parent not in dag:
                orphans.add(node_id)
                break
    return sorted(orphans)


def check_legal_transition(dag: dict[str, VerdictCapsule], from_node: str, to_node: str) -> bool:
    """Return True iff *to_node* is in ``from_node.allowed_next_nodes``.

    Raises :class:`MissingCapsule` if *from_node* is not in *dag*. The
    callable intentionally fails closed on unknown anchors; downstream
    code can wrap in try/except and demote to a soft warning if needed.
    """
    if from_node not in dag:
        msg = f"from_node {from_node!r} not in DAG"
        raise MissingCapsule(msg)
    return to_node in dag[from_node].allowed_next_nodes


# ---------------------------------------------------------------------------
# DAG-about-the-DAG emission
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DAGSelfVerdict:
    """The recursive self-anchor verdict written into the DAG artifact.

    ``merge_sha`` is None until the bootstrap PR itself lands on main;
    downstream PRs may rewrite it via a follow-up tooling pass.
    """

    node_id: str = "D002J-P2.5"
    decision: str = "VERDICT_DAG_BOOTSTRAPPED"
    merge_sha: str | None = None


_FORBIDDEN_CLAIMS_AGGREGATE: Final[tuple[str, ...]] = (
    "GeoSync predicts systemic crises",
    "GeoSync is bank-level validated",
    "D-002J rescues D-002H",
    "cross-asset coherence proves interbank contagion",
    "positive controls prove real-world performance",
    "source registry proves data quality",
    "crisis windows prove predictive power",
)


def emit_dag_verdict(
    dag: dict[str, VerdictCapsule],
    out_path: Path,
    self_verdict: DAGSelfVerdict | None = None,
    generated_at: str | None = None,
) -> None:
    """Write the DAG-about-the-DAG verdict JSON to *out_path*.

    The artifact's structure is fixed by ``schema_version`` :data:`SCHEMA_DAG`;
    its ``topological_order`` is computed deterministically via
    :func:`topological_order`; rejected/refused nodes are extracted via
    :func:`status`-filter; ``next_legal_nodes_from_main_head`` is the union
    of ``allowed_next_nodes`` for every node with no successor in the DAG.

    The artifact is written canonically (``sort_keys=True, indent=2``) so
    re-runs produce byte-identical output when the input DAG is unchanged.
    """
    if self_verdict is None:
        self_verdict = DAGSelfVerdict()
    # Compose nodes_count and topological order.
    order = topological_order(dag)
    rejected = sorted(
        n for n, c in dag.items() if c.status in {"TERMINAL_REJECTED", "TERMINAL_REFUSED"}
    )
    # Successor map: which nodes appear as a child of another in DAG.
    has_successor: set[str] = set()
    for capsule in dag.values():
        for parent in capsule.parent_nodes:
            has_successor.add(parent)
    leaf_ids = [n for n in order if n not in has_successor]
    next_legal: set[str] = set()
    for leaf in leaf_ids:
        next_legal.update(dag[leaf].allowed_next_nodes)
    # canonical_run_authorized must be False everywhere. Capsules do not
    # carry an authorization flag; absence is treated as False (project-
    # wide invariant). The DAG verdict records the conjunction
    # explicitly, so callers cannot infer authorization by silence.
    canonical_anywhere = False
    # Lineage transitions: a parent node whose lineage prefix differs
    # from a child's records an explicit cross-lineage transition. This
    # makes the honest "successor lineage opened BECAUSE the parent
    # terminally refused" relationship machine-readable and forbids any
    # silent rescue. is_rescue is always False by construction here: a
    # cross-lineage edge is a fresh-restart descent, never a rescue.
    lineage_transitions: dict[str, dict[str, Any]] = {}
    for child_id, child in dag.items():
        child_lineage = child_id.split("-", 1)[0]
        for parent_id in child.parent_nodes:
            if parent_id not in dag:
                continue
            parent_lineage = parent_id.split("-", 1)[0]
            if parent_lineage == child_lineage:
                continue
            parent_cap = dag[parent_id]
            # "D002K" -> "D-002K" (canonical study-id form). Generic:
            # split the leading "D" from the numeric+letter remainder.
            successor_lineage = (
                f"D-{child_lineage[1:]}"
                if child_lineage.startswith("D") and len(child_lineage) > 1
                else child_lineage
            )
            lineage_transitions[parent_id] = {
                "status": parent_cap.status,
                "successor_lineage": successor_lineage,
                "successor_root": child_id,
                "is_rescue": False,
            }
    ts = (
        generated_at
        if generated_at is not None
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_DAG,
        "generated_at": ts,
        "nodes_count": len(dag),
        "topological_order": order,
        "acyclic": True,
        "orphans": detect_orphans(dag),
        "rejected_nodes_retained": rejected,
        "next_legal_nodes_from_main_head": sorted(next_legal),
        "forbidden_claims_aggregate": list(_FORBIDDEN_CLAIMS_AGGREGATE),
        "canonical_run_authorized_anywhere": canonical_anywhere,
        "lineage_transitions": lineage_transitions,
        "dag_self_verdict": {
            "node_id": self_verdict.node_id,
            "decision": self_verdict.decision,
            "merge_sha": self_verdict.merge_sha,
        },
        "locked_governance_shas": dict(LOCKED_GOVERNANCE_SHAS),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_check(args: argparse.Namespace) -> int:
    """Validate the DAG; exit 0 on PASS, non-zero on any defect."""
    verdicts_dir = REPO_ROOT / VERDICTS_DIR_REL
    try:
        dag = load_dag(verdicts_dir)
        order = topological_order(dag)
        orphans = detect_orphans(dag)
    except VerdictDAGError as exc:
        sys.stderr.write(f"verdict_dag check FAILED: {exc}\n")
        return 2
    if orphans:
        sys.stderr.write(f"verdict_dag check FAILED: orphans={orphans}\n")
        return 2
    import hashlib

    for rel, expected in LOCKED_GOVERNANCE_SHAS.items():
        anchor = REPO_ROOT / rel
        if not anchor.exists():
            sys.stderr.write(f"verdict_dag check FAILED: locked governance anchor missing: {rel}\n")
            return 2
        actual = hashlib.sha256(anchor.read_bytes()).hexdigest()
        if actual != expected:
            sys.stderr.write(
                f"verdict_dag check FAILED: locked governance anchor tampered: {rel} "
                f"(expected {expected}, got {actual})\n"
            )
            return 2
    sys.stdout.write(f"verdict_dag check PASS: {len(dag)} nodes, order={order}\n")
    if args.verbose:
        for node_id in order:
            c = dag[node_id]
            sys.stdout.write(
                f"  {node_id}: phase={c.phase} PR=#{c.pr_number} "
                f"sha={c.merge_sha[:8]} decision={c.decision} status={c.status}\n"
            )
    return 0


def _cmd_emit(_args: argparse.Namespace) -> int:
    """Re-emit the DAG-about-the-DAG verdict from on-disk capsules."""
    verdicts_dir = REPO_ROOT / VERDICTS_DIR_REL
    out = REPO_ROOT / DAG_OUTPUT_REL
    try:
        dag = load_dag(verdicts_dir)
        emit_dag_verdict(dag, out, DAGSelfVerdict())
    except VerdictDAGError as exc:
        sys.stderr.write(f"verdict_dag emit FAILED: {exc}\n")
        return 2
    sys.stdout.write(f"verdict_dag emit OK: wrote {out}\n")
    return 0


def _cmd_render(_args: argparse.Namespace) -> int:
    """Re-render docs/research/D002J_LINEAGE_MAP.md from on-disk capsules."""
    # Local import to avoid a circular dependency at module import.
    from tools.governance.render_lineage import main as render_main

    return render_main([])


def main(argv: list[str] | None = None) -> int:
    """Module-level CLI entry point. Returns a Unix exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.governance.verdict_dag",
        description=(
            "Verdict-DAG governance tool for D-002J. Validates capsule "
            "schemas, the topological order, and locked governance SHAs."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check", help="validate the DAG fail-closed")
    p_check.add_argument("-v", "--verbose", action="store_true", help="emit per-node summary")
    p_check.set_defaults(func=_cmd_check)
    p_emit = sub.add_parser("emit", help="emit the DAG self-verdict JSON")
    p_emit.set_defaults(func=_cmd_emit)
    p_render = sub.add_parser("render", help="re-render the markdown lineage map")
    p_render.set_defaults(func=_cmd_render)
    args = parser.parse_args(argv)
    rc = args.func(args)
    if not isinstance(rc, int):
        return 0
    return rc


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
