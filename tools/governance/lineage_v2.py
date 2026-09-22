# Copyright (c) 2023-2026 Yaroslav Vasylenko
# SPDX-License-Identifier: MIT
"""Generic connected-lineage governance surface for D-002 successors.

The historical D002J verdict DAG v1 remains immutable. This v2 surface reads
all per-phase D002 letter-lineage capsules through the already-established v1
capsule parser and composes a generic J/K/L/... graph without mutating history.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from tools.governance.verdict_dag import (
    REPO_ROOT,
    VERDICTS_DIR_REL,
    VerdictCapsule,
    check_acyclic,
    detect_orphans,
    load_capsule,
    topological_order,
)

SCHEMA_V2: Final[str] = "D002-VERDICT-DAG-v2"
CAPSULE_RE: Final[re.Pattern[str]] = re.compile(r"^d002[a-z]_p.+_verdict_v1\.json$")
OUTPUT_REL: Final[str] = "artifacts/governance/verdicts/d002_lineage_dag_v2.json"
MAP_REL: Final[str] = "docs/research/D002_LINEAGE_MAP_V2.md"


class LineageV2Error(RuntimeError):
    """Fail-closed error for generic lineage composition."""


def discover_capsules(verdicts_dir: Path) -> list[Path]:
    """Return all per-phase D002 letter-lineage capsule paths deterministically."""
    if not verdicts_dir.is_dir():
        raise LineageV2Error(f"verdict directory missing: {verdicts_dir}")
    paths = sorted(p for p in verdicts_dir.iterdir() if p.is_file() and CAPSULE_RE.fullmatch(p.name))
    if not paths:
        raise LineageV2Error("no D002 per-phase verdict capsules discovered")
    return paths


def load_connected_dag(verdicts_dir: Path) -> dict[str, VerdictCapsule]:
    """Load all discovered capsules and reject duplicate node identifiers."""
    dag: dict[str, VerdictCapsule] = {}
    for path in discover_capsules(verdicts_dir):
        capsule = load_capsule(path)
        if capsule.node_id in dag:
            raise LineageV2Error(f"duplicate node_id: {capsule.node_id}")
        dag[capsule.node_id] = capsule
    if detect_orphans(dag):
        raise LineageV2Error(f"orphan nodes: {detect_orphans(dag)}")
    check_acyclic(dag)
    return dag


def lineage_id(node_id: str) -> str:
    """Convert D002L-P0 to D-002L and reject malformed ids."""
    prefix = node_id.split("-", 1)[0]
    if not re.fullmatch(r"D\d{3}[A-Z]", prefix):
        raise LineageV2Error(f"malformed node lineage prefix: {node_id}")
    return f"D-{prefix[1:]}"


def cross_lineage_transitions(dag: dict[str, VerdictCapsule]) -> dict[str, dict[str, Any]]:
    """Return explicit fresh-lineage edges; every transition is non-rescue."""
    result: dict[str, dict[str, Any]] = {}
    for child_id, child in dag.items():
        child_lineage = lineage_id(child_id)
        for parent_id in child.parent_nodes:
            parent_lineage = lineage_id(parent_id)
            if parent_lineage == child_lineage:
                continue
            parent = dag[parent_id]
            if parent.status not in {"TERMINAL_REFUSED", "TERMINAL_REJECTED"}:
                raise LineageV2Error(
                    f"cross-lineage restart requires rejected/refused parent: {parent_id}={parent.status}"
                )
            result[parent_id] = {
                "status": parent.status,
                "successor_lineage": child_lineage,
                "successor_root": child_id,
                "is_rescue": False,
            }
    return dict(sorted(result.items()))


def leaf_nodes(dag: dict[str, VerdictCapsule]) -> list[str]:
    parents = {p for c in dag.values() for p in c.parent_nodes}
    return [n for n in topological_order(dag) if n not in parents]


def next_legal_nodes(dag: dict[str, VerdictCapsule]) -> list[str]:
    out: set[str] = set()
    for leaf in leaf_nodes(dag):
        out.update(dag[leaf].allowed_next_nodes)
    return sorted(out)


def build_payload(dag: dict[str, VerdictCapsule], generated_at: str | None = None) -> dict[str, Any]:
    """Build canonical generic DAG summary without promoting scientific claims."""
    order = topological_order(dag)
    rejected = sorted(
        n for n, c in dag.items() if c.status in {"TERMINAL_REJECTED", "TERMINAL_REFUSED"}
    )
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": SCHEMA_V2,
        "generated_at": ts,
        "nodes_count": len(dag),
        "topological_order": order,
        "acyclic": True,
        "orphans": [],
        "rejected_nodes_retained": rejected,
        "next_legal_nodes_from_head": next_legal_nodes(dag),
        "lineage_transitions": cross_lineage_transitions(dag),
        "canonical_run_authorized_anywhere": False,
        "claim_boundary": (
            "Governance lineage only. A terminal PASS node does not prove scientific validity, "
            "predictive value, causal validity, trading alpha, or production readiness."
        ),
    }


def render_markdown(dag: dict[str, VerdictCapsule]) -> str:
    """Render deterministic human-readable generic lineage map."""
    order = topological_order(dag)
    transitions = cross_lineage_transitions(dag)
    lines = [
        "<!-- AUTO-GENERATED by tools.governance.lineage_v2 -->",
        "# D-002 Generic Verdict Lineage Map v2",
        "",
        "This map preserves historical terminal negatives and fresh-lineage restarts.",
        "It is governance evidence only; it is not a scientific-performance claim.",
        "",
        "## Topological order",
        "",
        "```text",
        " -> ".join(order),
        "```",
        "",
        "## Nodes",
        "",
        "| node | status | decision | parent | allowed next |",
        "|---|---|---|---|---|",
    ]
    for node in order:
        c = dag[node]
        parents = ", ".join(c.parent_nodes) or "—"
        nxt = ", ".join(c.allowed_next_nodes) or "—"
        lines.append(f"| `{node}` | `{c.status}` | `{c.decision}` | {parents} | {nxt} |")
    lines.extend(["", "## Cross-lineage transitions", ""])
    for parent, meta in transitions.items():
        lines.append(
            f"- `{parent}` ({meta['status']}) → `{meta['successor_root']}` "
            f"({meta['successor_lineage']}), `is_rescue=false`."
        )
    lines.extend(["", "## Next legal nodes", ""])
    nxt = next_legal_nodes(dag)
    lines.extend([f"- `{n}`" for n in nxt] if nxt else ["- none; graph sealed"])
    lines.append("")
    return "\n".join(lines)


def emit(verdicts_dir: Path, json_out: Path, md_out: Path, generated_at: str | None = None) -> None:
    dag = load_connected_dag(verdicts_dir)
    payload = build_payload(dag, generated_at=generated_at)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_markdown(dag), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.governance.lineage_v2")
    parser.add_argument("command", choices=["check", "emit"])
    args = parser.parse_args(argv)
    verdicts_dir = REPO_ROOT / VERDICTS_DIR_REL
    try:
        dag = load_connected_dag(verdicts_dir)
        if args.command == "emit":
            emit(verdicts_dir, REPO_ROOT / OUTPUT_REL, REPO_ROOT / MAP_REL)
        else:
            payload = build_payload(dag, generated_at="CHECK")
            sys.stdout.write(
                f"lineage_v2 PASS: nodes={payload['nodes_count']} "
                f"next={payload['next_legal_nodes_from_head']}\n"
            )
    except Exception as exc:
        sys.stderr.write(f"lineage_v2 FAIL: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
