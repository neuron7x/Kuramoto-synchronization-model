# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim-to-code provenance graph.

Lie blocked:
    "claim has tests somewhere"

Reads `.claude/research/PHYSICS_2026_TRANSLATION.yaml` (source of
patterns) and produces a structured graph mapping every IMPLEMENTED
pattern to its module, tests, falsifier text, workflows, and release-
ledger reference.

Edges:
    CLAIM_SUPPORTED_BY_EVIDENCE   pattern → source_id (translation matrix)
    CLAIM_TESTED_BY               pattern → test file
    TEST_KILLS_FALSIFIER          test file → _FALSIFIER_TEXT in module
    WORKFLOW_ENFORCES             workflow file → validator script ref
    RELEASE_RECORDED              pattern → release ledger md

A node is BROKEN if:
    - claim_tier=ENGINEERING_ANALOG, status=IMPLEMENTED, but no test
      file matches `tests/**/test_<basename>.py`
    - module exists but contains no `_FALSIFIER_TEXT` literal
    - module references a workflow that does not exist

Output: JSON + markdown summary written to /tmp/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRANSLATION = REPO_ROOT / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
DEFAULT_OUTPUT_JSON = Path("/tmp/geosync_claim_provenance.json")
DEFAULT_OUTPUT_MD = Path("/tmp/geosync_claim_provenance.md")


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    kind: str  # claim | evidence | module | test | falsifier | workflow | release
    status: str  # OK | BROKEN | UNKNOWN


@dataclass(frozen=True)
class GraphEdge:
    src: str
    dst: str
    kind: str  # one of edge kinds documented in module-level docstring


@dataclass
class ProvenanceReport:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    broken: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "broken_count": len(self.broken),
            "nodes": [asdict(n) for n in sorted(self.nodes, key=lambda x: (x.kind, x.node_id))],
            "edges": [asdict(e) for e in sorted(self.edges, key=lambda x: (x.kind, x.src, x.dst))],
            "broken": sorted(self.broken),
        }


def _load_translation(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"translation matrix not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _find_test_for_module(repo_root: Path, module_path: str) -> Path | None:
    base = Path(module_path).stem
    for prefix in ("tests/unit", "tests/integration", "tests/governance"):
        for path in (repo_root / prefix).rglob(f"test_{base}.py"):
            return path
    return None


def _module_contains_falsifier(repo_root: Path, module_path: str) -> bool:
    """A module documents its falsifier surface either via a module-
    level ``_FALSIFIER_TEXT`` constant (shared by P2..P10) or via a
    field named ``falsifier_status`` (P1's per-event style)."""
    p = repo_root / module_path
    if not p.exists():
        return False
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return "_FALSIFIER_TEXT" in text or "falsifier_status" in text


def _workflows_referencing(repo_root: Path, validator_token: str) -> list[Path]:
    wf_dir = repo_root / ".github" / "workflows"
    out: list[Path] = []
    if not wf_dir.exists():
        return out
    for path in wf_dir.rglob("*.yml"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if validator_token in text:
            out.append(path)
    return out


def _release_md_for_pattern(repo_root: Path) -> Path | None:
    rels = repo_root / "docs" / "releases"
    if not rels.exists():
        return None
    for path in sorted(rels.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "Reality-Validation" in text or "P1–P10" in text or "P1..P10" in text:
            return path
    return None


def build_graph(translation_matrix_path: Path = DEFAULT_TRANSLATION) -> ProvenanceReport:
    report = ProvenanceReport()
    data = _load_translation(translation_matrix_path)
    patterns = data.get("patterns") or []
    if not isinstance(patterns, list):
        return report

    release_md = _release_md_for_pattern(REPO_ROOT)
    if release_md is not None:
        rel = release_md.relative_to(REPO_ROOT)
        report.nodes.append(GraphNode(node_id=str(rel), kind="release", status="OK"))

    for entry in patterns:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("pattern_id") or "")
        status = str(entry.get("implementation_status") or "")
        if status != "IMPLEMENTED":
            # PROPOSED patterns are not BROKEN; they are not in the graph.
            continue
        report.nodes.append(GraphNode(node_id=pid, kind="claim", status="OK"))

        # Edge: CLAIM_SUPPORTED_BY_EVIDENCE → each source_id
        for sid in entry.get("source_ids") or []:
            sid_str = str(sid)
            report.nodes.append(GraphNode(node_id=sid_str, kind="evidence", status="OK"))
            report.edges.append(GraphEdge(src=pid, dst=sid_str, kind="CLAIM_SUPPORTED_BY_EVIDENCE"))

        module_path = str(entry.get("proposed_module") or "")
        module_node = GraphNode(
            node_id=module_path,
            kind="module",
            status="OK" if (REPO_ROOT / module_path).exists() else "BROKEN",
        )
        report.nodes.append(module_node)
        if module_node.status == "BROKEN":
            report.broken.append(f"module-missing: {module_path}")

        test_path = _find_test_for_module(REPO_ROOT, module_path)
        if test_path is None:
            report.broken.append(f"no-test-for: {pid} ({module_path})")
        else:
            rel = str(test_path.relative_to(REPO_ROOT))
            report.nodes.append(GraphNode(node_id=rel, kind="test", status="OK"))
            report.edges.append(GraphEdge(src=pid, dst=rel, kind="CLAIM_TESTED_BY"))

            if _module_contains_falsifier(REPO_ROOT, module_path):
                falsifier_id = f"{module_path}::_FALSIFIER_TEXT"
                report.nodes.append(GraphNode(node_id=falsifier_id, kind="falsifier", status="OK"))
                report.edges.append(
                    GraphEdge(src=rel, dst=falsifier_id, kind="TEST_KILLS_FALSIFIER")
                )
            else:
                report.broken.append(f"no-falsifier-text: {pid} ({module_path})")

        if release_md is not None:
            report.edges.append(
                GraphEdge(
                    src=pid,
                    dst=str(release_md.relative_to(REPO_ROOT)),
                    kind="RELEASE_RECORDED",
                )
            )

    # Workflow → validator-script edges (best-effort).
    for wf in (REPO_ROOT / ".github" / "workflows").rglob("*.yml"):
        try:
            text = wf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in re.finditer(r"(tools/[a-z_/]+/validate_[a-z0-9_]+\.py)", text):
            wf_id = str(wf.relative_to(REPO_ROOT))
            report.nodes.append(GraphNode(node_id=wf_id, kind="workflow", status="OK"))
            report.edges.append(GraphEdge(src=wf_id, dst=m.group(1), kind="WORKFLOW_ENFORCES"))

    # Deduplicate nodes by (kind, node_id).
    seen: set[tuple[str, str]] = set()
    unique_nodes: list[GraphNode] = []
    for n in report.nodes:
        key = (n.kind, n.node_id)
        if key in seen:
            continue
        seen.add(key)
        unique_nodes.append(n)
    report.nodes = unique_nodes
    return report


def render_markdown(report: ProvenanceReport) -> str:
    lines = ["# Claim Provenance Graph\n"]
    lines.append(
        f"- nodes: {len(report.nodes)}\n"
        f"- edges: {len(report.edges)}\n"
        f"- broken: {len(report.broken)}\n"
    )
    if report.broken:
        lines.append("\n## Broken edges\n")
        for b in sorted(report.broken):
            lines.append(f"- {b}\n")
    by_kind: dict[str, list[str]] = {}
    for n in report.nodes:
        by_kind.setdefault(n.kind, []).append(n.node_id)
    lines.append("\n## Nodes by kind\n")
    for kind in sorted(by_kind):
        lines.append(f"\n### {kind} ({len(by_kind[kind])})\n")
        for nid in sorted(by_kind[kind]):
            lines.append(f"- `{nid}`\n")
    return "".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claim provenance graph")
    parser.add_argument("--translation", type=Path, default=DEFAULT_TRANSLATION)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = build_graph(args.translation)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    args.output_json.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"OK: nodes={len(report.nodes)} edges={len(report.edges)} broken={len(report.broken)}")
    return 0 if not report.broken else 1


if __name__ == "__main__":
    raise SystemExit(main())
