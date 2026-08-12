# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Build a machine-readable governance evidence graph.

This module is intentionally a graph projection over governance/INSTRUMENTS.yaml.
It does not invent a second registry. It exposes the existing instrument evidence
chain as nodes, edges, and explicit negative-evidence arrays.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

CLAIM_BOUNDARY = "descriptor_only_not_predictor"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"registry not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("registry root must be a mapping")
    if not isinstance(data.get("instruments"), list):
        raise ValueError("registry missing instruments list")
    return data


def _node(kind: str, ident: str, **attrs: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"id": f"{kind}:{ident}", "kind": kind, "ref": ident}
    body.update(attrs)
    return body


def _edge(src: str, dst: str, relation: str) -> dict[str, str]:
    return {"from": src, "to": dst, "relation": relation}


def _acceptor_paths(root: Path, acceptor_rel: str) -> tuple[set[str], list[dict[str, Any]]]:
    path = root / acceptor_rel
    if not path.is_file():
        return set(), []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return set(), []
    diff_scope = data.get("diff_scope") or {}
    if not isinstance(diff_scope, dict):
        return set(), []
    changed = diff_scope.get("changed_files") or []
    paths = {str(item.get("path")) for item in changed if isinstance(item, dict)}
    evidence = data.get("evidence") or []
    return paths, [item for item in evidence if isinstance(item, dict)]


def build_evidence_graph(registry: dict[str, Any], *, root: Path) -> dict[str, Any]:
    required_boundary = str(registry.get("claim_boundary_required") or CLAIM_BOUNDARY)
    graph: dict[str, Any] = {
        "nodes": [],
        "edges": [],
        "dangling_nodes": [],
        "stale_hashes": [],
        "missing_tests": [],
        "missing_acceptors": [],
        "missing_artifacts": [],
        "claim_boundary_violations": [],
    }

    for inst in registry.get("instruments", []):
        if not isinstance(inst, dict):
            graph["dangling_nodes"].append("instrument:<malformed>")
            continue

        iid = str(inst.get("id") or "<unnamed>")
        inst_id = f"instrument:{iid}"
        graph["nodes"].append(_node("instrument", iid))

        pr = str(inst.get("pr", ""))
        merge_commit = str(inst.get("merge_commit", ""))
        module = str(inst.get("module", ""))
        test_file = str(inst.get("test_file", ""))
        acceptor = str(inst.get("acceptor", ""))
        source_sha = str(inst.get("source_sha256", ""))
        boundary = str(inst.get("claim_boundary", ""))

        references = [
            ("pr", pr, "declared_by"),
            ("merge_commit", merge_commit, "merged_as"),
            ("module", module, "implements"),
            ("source_hash", source_sha, "locked_by"),
            ("test_file", test_file, "tested_by"),
            ("acceptor", acceptor, "accepted_by"),
            ("claim_boundary", boundary, "bounded_by"),
        ]
        for kind, ref, relation in references:
            if ref:
                nid = f"{kind}:{ref}"
                graph["nodes"].append(_node(kind, ref))
                graph["edges"].append(_edge(inst_id, nid, relation))
            else:
                graph["dangling_nodes"].append(f"{inst_id}:{kind}:missing")

        module_path = root / module
        if not module or not module_path.is_file():
            graph["dangling_nodes"].append(f"module:{module}")
        else:
            actual_sha = sha256_file(module_path)
            if source_sha != actual_sha:
                graph["stale_hashes"].append(
                    {
                        "instrument": iid,
                        "module": module,
                        "expected": source_sha,
                        "actual": actual_sha,
                    }
                )
            module_text = module_path.read_text(encoding="utf-8")
            if boundary != required_boundary or required_boundary not in module_text:
                graph["claim_boundary_violations"].append(
                    {"instrument": iid, "module": module, "boundary": boundary}
                )

        if not test_file or not (root / test_file).is_file():
            graph["missing_tests"].append({"instrument": iid, "test_file": test_file})

        acceptor_path = root / acceptor
        if not acceptor or not acceptor_path.is_file():
            graph["missing_acceptors"].append({"instrument": iid, "acceptor": acceptor})
            graph["missing_artifacts"].append({"instrument": iid, "artifact": "acceptor_evidence"})
            continue

        acceptor_changed, evidence = _acceptor_paths(root, acceptor)
        if module and module not in acceptor_changed:
            graph["dangling_nodes"].append(f"acceptor:{acceptor}:does_not_bind:{module}")
        if not evidence:
            graph["missing_artifacts"].append({"instrument": iid, "artifact": "acceptor_evidence"})
        for index, item in enumerate(evidence):
            artifact_ref = str(item.get("path") or f"{acceptor}#evidence[{index}]")
            artifact_id = f"artifact:{artifact_ref}"
            graph["nodes"].append(
                _node("artifact", artifact_ref, sha256=str(item.get("sha256", "")))
            )
            graph["edges"].append(_edge(inst_id, artifact_id, "evidenced_by"))

        for falsifier in inst.get("falsifiers") or []:
            falsifier_ref = str(falsifier)
            node_id = f"pytest_node:{falsifier_ref}"
            graph["nodes"].append(_node("pytest_node", falsifier_ref))
            graph["edges"].append(_edge(inst_id, node_id, "falsified_by"))

    return graph
